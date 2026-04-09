from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from backend.models.database import SessionLocal, Appointment, Business, ReminderSettings
from backend.services.sms import send_sms
from backend.services.ai_messages import generate_reminder_message
from backend.services.stripe_billing import is_subscription_active
from datetime import datetime, timedelta
import pytz
import logging

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def check_and_send_reminders():
    """Main job: check for appointments needing reminders and send them."""
    db: Session = SessionLocal()
    try:
        now = datetime.utcnow()
        window_24h_start = now + timedelta(hours=23, minutes=45)
        window_24h_end   = now + timedelta(hours=24, minutes=15)
        window_2h_start  = now + timedelta(hours=1, minutes=45)
        window_2h_end    = now + timedelta(hours=2, minutes=15)

        # 24-hour reminders
        appts_24h = db.query(Appointment).filter(
            Appointment.scheduled_at >= window_24h_start,
            Appointment.scheduled_at <= window_24h_end,
            Appointment.reminder_24h_sent == False,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).all()

        # 2-hour reminders
        appts_2h = db.query(Appointment).filter(
            Appointment.scheduled_at >= window_2h_start,
            Appointment.scheduled_at <= window_2h_end,
            Appointment.reminder_2h_sent == False,
            Appointment.status.in_(["scheduled", "confirmed"])
        ).all()

        for appt in appts_24h:
            _send_reminder(db, appt, "24h")

        for appt in appts_2h:
            _send_reminder(db, appt, "2h")

        # Mark no-shows (appointments that passed 30+ min ago still "scheduled")
        no_shows = db.query(Appointment).filter(
            Appointment.scheduled_at <= now - timedelta(minutes=30),
            Appointment.status == "scheduled"
        ).all()
        for appt in no_shows:
            appt.status = "no_show"
            logger.info(f"Marked appointment {appt.id} as no_show")
        db.commit()

    except Exception as e:
        logger.error(f"Scheduler error: {e}")
    finally:
        db.close()

def _send_reminder(db: Session, appt: Appointment, reminder_type: str):
    """Send a single reminder for an appointment."""
    business = db.query(Business).filter(Business.id == appt.business_id).first()
    if not business:
        return

    # Check subscription
    if not is_subscription_active(business):
        return

    # Get reminder settings
    settings_obj = db.query(ReminderSettings).filter(
        ReminderSettings.business_id == business.id
    ).first()

    if settings_obj:
        if reminder_type == "24h" and not settings_obj.send_24h:
            return
        if reminder_type == "2h" and not settings_obj.send_2h:
            return

    # Skip opted-out clients
    if appt.client.opt_out:
        return

    # Format appointment time
    try:
        tz = pytz.timezone(business.timezone)
        local_time = appt.scheduled_at.replace(tzinfo=pytz.utc).astimezone(tz)
        time_str = local_time.strftime("%A %b %d at %I:%M %p")
    except:
        time_str = appt.scheduled_at.strftime("%Y-%m-%d %H:%M")

    # Generate AI message or use custom
    use_ai = settings_obj.ai_personalize if settings_obj else True
    custom = settings_obj.custom_message if settings_obj else None

    if use_ai:
        message = generate_reminder_message(
            business_name=business.name,
            business_type=business.business_type,
            client_name=appt.client.name,
            service=appt.service or "appointment",
            scheduled_at=time_str,
            reminder_type=reminder_type,
            custom_base=custom
        )
    else:
        first = appt.client.name.split()[0]
        message = custom or (
            f"Hi {first}! Reminder: {appt.service or 'appointment'} at {business.name} "
            f"on {time_str}. Reply CONFIRM or CANCEL."
        )

    # Store message on appointment
    appt.reminder_message = message

    # Send SMS
    result = send_sms(
        db=db,
        business_id=business.id,
        to_phone=appt.client.phone,
        message=message,
        appointment_id=appt.id
    )

    if result.get("success"):
        if reminder_type == "24h":
            appt.reminder_24h_sent = True
        else:
            appt.reminder_2h_sent = True
        logger.info(f"Sent {reminder_type} reminder for appt {appt.id} to {appt.client.name}")
    else:
        logger.error(f"Failed to send reminder for appt {appt.id}: {result.get('error')}")

    db.commit()

def start_scheduler():
    scheduler.add_job(
        check_and_send_reminders,
        IntervalTrigger(minutes=15),
        id="reminder_check",
        replace_existing=True
    )
    scheduler.start()
    logger.info("Reminder scheduler started - checking every 15 minutes")

def stop_scheduler():
    scheduler.shutdown()
