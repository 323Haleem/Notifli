from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from backend.models.database import Business, ReminderSettings
from backend.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto", bcrypt__rounds=12)

def hash_password(password: str) -> str:
    # Truncate to 72 bytes (not characters) to satisfy bcrypt limit
    # Encode to UTF-8, truncate to 72 bytes, decode back
    password_bytes = password.encode('utf-8')[:72]
    truncated = password_bytes.decode('utf-8', errors='ignore')
    return pwd_context.hash(truncated)

def verify_password(plain: str, hashed: str) -> bool:
    # Truncate to 72 bytes for verification (same as hashing)
    password_bytes = plain.encode('utf-8')[:72]
    truncated = password_bytes.decode('utf-8', errors='ignore')
    try:
        return pwd_context.verify(truncated, hashed)
    except Exception:
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None

def register_business(db: Session, name: str, email: str, password: str, business_type: str = "general", timezone: str = "America/New_York") -> Business:
    existing = db.query(Business).filter(Business.email == email).first()
    if existing:
        raise ValueError("Email already registered")
    
    # Validate password minimum length
    if len(password) < 6:
        raise ValueError("Password must be at least 6 characters")
    # No max length check needed - hash_password truncates to 72 bytes automatically

    trial_ends = datetime.utcnow() + timedelta(days=settings.FREE_TRIAL_DAYS)
    biz = Business(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        business_type=business_type,
        timezone=timezone,
        trial_ends_at=trial_ends,
        subscription_status="trial"
    )
    db.add(biz)
    db.flush()

    # Create default reminder settings
    reminder_settings = ReminderSettings(business_id=biz.id)
    db.add(reminder_settings)
    db.commit()
    db.refresh(biz)
    return biz

def authenticate_business(db: Session, email: str, password: str) -> Optional[Business]:
    biz = db.query(Business).filter(Business.email == email).first()
    if not biz or not verify_password(password, biz.hashed_password):
        return None
    return biz

def get_current_business(db: Session, token: str) -> Optional[Business]:
    payload = decode_token(token)
    if not payload:
        return None
    email = payload.get("sub")
    if not email:
        return None
    return db.query(Business).filter(Business.email == email).first()
