from twilio.rest import Client as TwilioClient
from twilio.base.exceptions import TwilioRestException
from sqlalchemy.orm import Session
from backend.core.config import settings
from backend.models.database import SMSLog, Appointment
from datetime import datetime
import re

def get_twilio_client():
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        return None
    return TwilioClient(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

def format_phone(phone: str) -> str:
    """Normalize phone number to E.164 format."""
    digits = re.sub(r'\D', '', phone)
    if len(digits) == 10:
        return f"+1{digits}"
    elif len(digits) == 11 and digits.startswith('1'):
        return f"+{digits}"
    return f"+{digits}"

def send_sms(
    db: Session,
    business_id: int,
    to_phone: str,
    message: str,
    appointment_id: int = None
) -> dict:
    """Send an SMS and log it."""
    formatted_phone = format_phone(to_phone)

    log = SMSLog(
        business_id=business_id,
        appointment_id=appointment_id,
        client_phone=formatted_phone,
        message=message,
        direction="outbound",
        status="pending"
    )
    db.add(log)
    db.flush()

    client = get_twilio_client()
    if not client:
        # Demo mode - log but don't actually send
        log.status = "demo"
        log.twilio_sid = f"DEMO_{log.id}"
        db.commit()
        return {"success": True, "demo": True, "message_sid": log.twilio_sid}

    try:
        twilio_msg = client.messages.create(
            body=message,
            from_=settings.TWILIO_PHONE_NUMBER,
            to=formatted_phone
        )
        log.status = "sent"
        log.twilio_sid = twilio_msg.sid
        db.commit()
        return {"success": True, "demo": False, "message_sid": twilio_msg.sid}

    except TwilioRestException as e:
        log.status = "failed"
        db.commit()
        return {"success": False, "error": str(e)}

def handle_inbound_sms(db: Session, from_phone: str, body: str, business_id: int = None):
    """Handle replies from clients (CONFIRM, CANCEL, STOP)."""
    body_upper = body.strip().upper()
    formatted = format_phone(from_phone)

    # Log inbound
    log = SMSLog(
        business_id=business_id or 0,
        client_phone=formatted,
        message=body,
        direction="inbound",
        status="received"
    )
    db.add(log)

    # Handle opt-out
    if body_upper in ["STOP", "UNSUBSCRIBE", "QUIT", "CANCEL ALL"]:
        from backend.models.database import Client
        client = db.query(Client).filter(Client.phone.contains(formatted[-10:])).first()
        if client:
            client.opt_out = True
        db.commit()
        return {"action": "opt_out"}

    # Handle confirmation
    if body_upper in ["CONFIRM", "YES", "Y", "1"]:
        # Find most recent upcoming appointment for this phone
        from backend.models.database import Client, Appointment
        from datetime import datetime
        client = db.query(Client).filter(Client.phone.contains(formatted[-10:])).first()
        if client:
            appt = db.query(Appointment).filter(
                Appointment.client_id == client.id,
                Appointment.scheduled_at >= datetime.utcnow(),
                Appointment.status == "scheduled"
            ).order_by(Appointment.scheduled_at).first()
            if appt:
                appt.status = "confirmed"
                db.commit()
                return {"action": "confirmed", "appointment_id": appt.id}

    if body_upper in ["CANCEL", "NO", "N", "2"]:
        from backend.models.database import Client, Appointment
        client = db.query(Client).filter(Client.phone.contains(formatted[-10:])).first()
        if client:
            appt = db.query(Appointment).filter(
                Appointment.client_id == client.id,
                Appointment.scheduled_at >= datetime.utcnow(),
                Appointment.status.in_(["scheduled", "confirmed"])
            ).order_by(Appointment.scheduled_at).first()
            if appt:
                appt.status = "cancelled"
                db.commit()
                return {"action": "cancelled", "appointment_id": appt.id}

    db.commit()
    return {"action": "unknown"}
