from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
from backend.core.config import settings
import os

# Detect database type and configure engine accordingly
db_url = settings.DATABASE_URL
is_postgres = db_url and db_url.startswith("postgresql")

if is_postgres:
    # PostgreSQL configuration
    engine = create_engine(
        db_url,
        pool_pre_ping=True,  # Auto-reconnect on connection loss
        pool_size=10,
        max_overflow=20
    )
else:
    # SQLite configuration (local dev only)
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False}
    )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ── Models ─────────────────────────────────────────────────────────────

class Business(Base):
    __tablename__ = "businesses"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    phone = Column(String, nullable=True)
    business_type = Column(String, default="general")  # dental, salon, gym, etc.
    timezone = Column(String, default="America/New_York")
    is_active = Column(Boolean, default=True)
    trial_ends_at = Column(DateTime, nullable=True)
    stripe_customer_id = Column(String, nullable=True)
    stripe_subscription_id = Column(String, nullable=True)
    subscription_status = Column(String, default="trial")  # trial, active, cancelled
    created_at = Column(DateTime, default=datetime.utcnow)

    clients = relationship("Client", back_populates="business", cascade="all, delete")
    appointments = relationship("Appointment", back_populates="business", cascade="all, delete")
    reminder_settings = relationship("ReminderSettings", back_populates="business", uselist=False, cascade="all, delete")

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    name = Column(String, nullable=False)
    phone = Column(String, nullable=False)
    email = Column(String, nullable=True)
    notes = Column(Text, nullable=True)
    opt_out = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="clients")
    appointments = relationship("Appointment", back_populates="client")

class Appointment(Base):
    __tablename__ = "appointments"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    client_id = Column(Integer, ForeignKey("clients.id"), nullable=False)
    service = Column(String, nullable=True)
    scheduled_at = Column(DateTime, nullable=False)
    duration_minutes = Column(Integer, default=60)
    status = Column(String, default="scheduled")  # scheduled, confirmed, cancelled, no_show, completed
    reminder_24h_sent = Column(Boolean, default=False)
    reminder_2h_sent = Column(Boolean, default=False)
    reminder_message = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="appointments")
    client = relationship("Client", back_populates="appointments")
    sms_logs = relationship("SMSLog", back_populates="appointment", cascade="all, delete")

class SMSLog(Base):
    __tablename__ = "sms_logs"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), nullable=False)
    appointment_id = Column(Integer, ForeignKey("appointments.id"), nullable=True)
    client_phone = Column(String, nullable=False)
    message = Column(Text, nullable=False)
    direction = Column(String, default="outbound")  # outbound, inbound
    status = Column(String, default="sent")  # sent, delivered, failed
    twilio_sid = Column(String, nullable=True)
    sent_at = Column(DateTime, default=datetime.utcnow)

    appointment = relationship("Appointment", back_populates="sms_logs")

class ReminderSettings(Base):
    __tablename__ = "reminder_settings"
    id = Column(Integer, primary_key=True, index=True)
    business_id = Column(Integer, ForeignKey("businesses.id"), unique=True, nullable=False)
    send_24h = Column(Boolean, default=True)
    send_2h = Column(Boolean, default=True)
    custom_message = Column(Text, nullable=True)
    include_cancel_link = Column(Boolean, default=True)
    include_reschedule_link = Column(Boolean, default=False)
    ai_personalize = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    business = relationship("Business", back_populates="reminder_settings")


def create_tables():
    Base.metadata.create_all(bind=engine)
