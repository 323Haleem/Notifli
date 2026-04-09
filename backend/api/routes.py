from fastapi import APIRouter, Depends, HTTPException, Request, Header, Body
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, EmailStr

from backend.models.database import get_db, Business, Client, Appointment, ReminderSettings, SMSLog
from backend.services import auth, sms, stripe_billing
from backend.services.ai_messages import generate_reminder_message
from backend.core.config import settings

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

# ── Pydantic Schemas ───────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    name: str
    email: str
    password: str
    business_type: str = "general"
    timezone: str = "America/New_York"

class LoginRequest(BaseModel):
    email: str
    password: str

class ClientCreate(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    notes: Optional[str] = None

class AppointmentCreate(BaseModel):
    client_id: int
    service: Optional[str] = None
    scheduled_at: datetime
    duration_minutes: int = 60
    notes: Optional[str] = None

class AppointmentUpdate(BaseModel):
    status: Optional[str] = None
    service: Optional[str] = None
    scheduled_at: Optional[datetime] = None
    notes: Optional[str] = None

class ReminderSettingsUpdate(BaseModel):
    send_24h: Optional[bool] = None
    send_2h: Optional[bool] = None
    custom_message: Optional[str] = None
    ai_personalize: Optional[bool] = None
    include_cancel_link: Optional[bool] = None

# ── Auth dependency ────────────────────────────────────────────────────

def get_current_biz(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> Business:
    biz = auth.get_current_business(db, token)
    if not biz:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return biz

# ── Auth Routes ────────────────────────────────────────────────────────

@router.post("/auth/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    try:
        biz = auth.register_business(db, req.name, req.email, req.password, req.business_type, req.timezone)
        token = auth.create_access_token({"sub": biz.email})
        return {
            "access_token": token,
            "token_type": "bearer",
            "business": {
                "id": biz.id, "name": biz.name, "email": biz.email,
                "business_type": biz.business_type, "subscription_status": biz.subscription_status,
                "trial_ends_at": biz.trial_ends_at.isoformat() if biz.trial_ends_at else None
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/auth/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    biz = auth.authenticate_business(db, req.email, req.password)
    if not biz:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = auth.create_access_token({"sub": biz.email})
    return {
        "access_token": token,
        "token_type": "bearer",
        "business": {
            "id": biz.id, "name": biz.name, "email": biz.email,
            "business_type": biz.business_type, "subscription_status": biz.subscription_status,
            "trial_ends_at": biz.trial_ends_at.isoformat() if biz.trial_ends_at else None
        }
    }

@router.get("/auth/me")
def me(biz: Business = Depends(get_current_biz)):
    active = stripe_billing.is_subscription_active(biz)
    return {
        "id": biz.id, "name": biz.name, "email": biz.email,
        "business_type": biz.business_type, "timezone": biz.timezone,
        "subscription_status": biz.subscription_status,
        "trial_ends_at": biz.trial_ends_at.isoformat() if biz.trial_ends_at else None,
        "is_active": active
    }

# ── Client Routes ──────────────────────────────────────────────────────

@router.get("/clients")
def list_clients(biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    clients = db.query(Client).filter(Client.business_id == biz.id).all()
    return [{"id": c.id, "name": c.name, "phone": c.phone, "email": c.email,
             "notes": c.notes, "opt_out": c.opt_out} for c in clients]

@router.post("/clients")
def create_client(req: ClientCreate, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    client = Client(business_id=biz.id, name=req.name, phone=req.phone,
                    email=req.email, notes=req.notes)
    db.add(client)
    db.commit()
    db.refresh(client)
    return {"id": client.id, "name": client.name, "phone": client.phone}

@router.delete("/clients/{client_id}")
def delete_client(client_id: int, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == client_id, Client.business_id == biz.id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    db.delete(client)
    db.commit()
    return {"ok": True}

# ── Appointment Routes ─────────────────────────────────────────────────

@router.get("/appointments")
def list_appointments(biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    appts = db.query(Appointment).filter(
        Appointment.business_id == biz.id
    ).order_by(Appointment.scheduled_at).all()
    return [{
        "id": a.id, "client_id": a.client_id,
        "client_name": a.client.name if a.client else "",
        "client_phone": a.client.phone if a.client else "",
        "service": a.service, "scheduled_at": a.scheduled_at.isoformat(),
        "duration_minutes": a.duration_minutes, "status": a.status,
        "reminder_24h_sent": a.reminder_24h_sent, "reminder_2h_sent": a.reminder_2h_sent,
        "notes": a.notes
    } for a in appts]

@router.post("/appointments")
def create_appointment(req: AppointmentCreate, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    client = db.query(Client).filter(Client.id == req.client_id, Client.business_id == biz.id).first()
    if not client:
        raise HTTPException(status_code=404, detail="Client not found")
    appt = Appointment(
        business_id=biz.id, client_id=req.client_id,
        service=req.service, scheduled_at=req.scheduled_at,
        duration_minutes=req.duration_minutes, notes=req.notes
    )
    db.add(appt)
    db.commit()
    db.refresh(appt)
    return {"id": appt.id, "status": appt.status, "scheduled_at": appt.scheduled_at.isoformat()}

@router.patch("/appointments/{appt_id}")
def update_appointment(appt_id: int, req: AppointmentUpdate, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    appt = db.query(Appointment).filter(Appointment.id == appt_id, Appointment.business_id == biz.id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if req.status: appt.status = req.status
    if req.service: appt.service = req.service
    if req.scheduled_at: appt.scheduled_at = req.scheduled_at
    if req.notes: appt.notes = req.notes
    db.commit()
    return {"ok": True, "id": appt.id, "status": appt.status}

@router.delete("/appointments/{appt_id}")
def delete_appointment(appt_id: int, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    appt = db.query(Appointment).filter(Appointment.id == appt_id, Appointment.business_id == biz.id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(appt)
    db.commit()
    return {"ok": True}

@router.post("/appointments/{appt_id}/send-reminder")
def send_reminder_now(appt_id: int, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    appt = db.query(Appointment).filter(Appointment.id == appt_id, Appointment.business_id == biz.id).first()
    if not appt:
        raise HTTPException(status_code=404, detail="Not found")
    if not appt.client:
        raise HTTPException(status_code=400, detail="No client attached")

    time_str = appt.scheduled_at.strftime("%A %b %d at %I:%M %p")
    message = generate_reminder_message(
        business_name=biz.name, business_type=biz.business_type,
        client_name=appt.client.name, service=appt.service or "appointment",
        scheduled_at=time_str, reminder_type="manual"
    )
    result = sms.send_sms(db, biz.id, appt.client.phone, message, appt.id)
    return {"ok": result.get("success"), "message": message, "demo": result.get("demo", False)}

# ── Reminder Settings ──────────────────────────────────────────────────

@router.get("/settings/reminders")
def get_reminder_settings(biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    s = db.query(ReminderSettings).filter(ReminderSettings.business_id == biz.id).first()
    if not s:
        s = ReminderSettings(business_id=biz.id)
        db.add(s); db.commit(); db.refresh(s)
    return {"send_24h": s.send_24h, "send_2h": s.send_2h,
            "custom_message": s.custom_message, "ai_personalize": s.ai_personalize,
            "include_cancel_link": s.include_cancel_link}

@router.patch("/settings/reminders")
def update_reminder_settings(req: ReminderSettingsUpdate, biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    s = db.query(ReminderSettings).filter(ReminderSettings.business_id == biz.id).first()
    if not s:
        s = ReminderSettings(business_id=biz.id); db.add(s)
    if req.send_24h is not None: s.send_24h = req.send_24h
    if req.send_2h is not None: s.send_2h = req.send_2h
    if req.custom_message is not None: s.custom_message = req.custom_message
    if req.ai_personalize is not None: s.ai_personalize = req.ai_personalize
    if req.include_cancel_link is not None: s.include_cancel_link = req.include_cancel_link
    db.commit()
    return {"ok": True}

# ── SMS Logs ───────────────────────────────────────────────────────────

@router.get("/sms-logs")
def get_sms_logs(biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    logs = db.query(SMSLog).filter(SMSLog.business_id == biz.id).order_by(SMSLog.sent_at.desc()).limit(100).all()
    return [{"id": l.id, "client_phone": l.client_phone, "message": l.message,
             "direction": l.direction, "status": l.status, "sent_at": l.sent_at.isoformat()} for l in logs]

# ── Dashboard Stats ────────────────────────────────────────────────────

@router.get("/dashboard/stats")
def dashboard_stats(biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    now = datetime.utcnow()
    total_clients = db.query(Client).filter(Client.business_id == biz.id).count()
    upcoming = db.query(Appointment).filter(
        Appointment.business_id == biz.id,
        Appointment.scheduled_at >= now,
        Appointment.status.in_(["scheduled", "confirmed"])
    ).count()
    no_shows_month = db.query(Appointment).filter(
        Appointment.business_id == biz.id,
        Appointment.status == "no_show",
        Appointment.scheduled_at >= datetime(now.year, now.month, 1)
    ).count()
    reminders_sent = db.query(SMSLog).filter(
        SMSLog.business_id == biz.id,
        SMSLog.direction == "outbound"
    ).count()
    return {
        "total_clients": total_clients,
        "upcoming_appointments": upcoming,
        "no_shows_this_month": no_shows_month,
        "total_reminders_sent": reminders_sent,
        "subscription_status": biz.subscription_status,
        "trial_ends_at": biz.trial_ends_at.isoformat() if biz.trial_ends_at else None,
        "is_active": stripe_billing.is_subscription_active(biz)
    }

# ── Billing ────────────────────────────────────────────────────────────

@router.post("/billing/checkout")
def start_checkout(biz: Business = Depends(get_current_biz), db: Session = Depends(get_db)):
    url = stripe_billing.create_checkout_session(
        biz,
        success_url=f"{settings.APP_URL}/dashboard?payment=success",
        cancel_url=f"{settings.APP_URL}/pricing?cancelled=true"
    )
    return {"checkout_url": url}

@router.post("/billing/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig = request.headers.get("stripe-signature", "")
    result = stripe_billing.handle_webhook(payload, sig, db)
    return result

# ── Twilio Webhook (inbound SMS) ───────────────────────────────────────

@router.post("/sms/inbound")
async def inbound_sms(request: Request, db: Session = Depends(get_db)):
    form = await request.form()
    from_phone = form.get("From", "")
    body = form.get("Body", "")
    result = sms.handle_inbound_sms(db, from_phone, body)
    # Return TwiML
    return JSONResponse(content={"ok": True, "action": result.get("action")})
