import stripe
from sqlalchemy.orm import Session
from backend.core.config import settings
from backend.models.database import Business
from datetime import datetime

# Only initialize Stripe if we have a key
if settings.STRIPE_SECRET_KEY and settings.STRIPE_SECRET_KEY != "sk_test" and not settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
    stripe.api_key = settings.STRIPE_SECRET_KEY
else:
    stripe.api_key = None

def create_customer(business: Business) -> str:
    """Create a Stripe customer for a business."""
    if not settings.STRIPE_SECRET_KEY:
        return "demo_customer"
    customer = stripe.Customer.create(
        email=business.email,
        name=business.name,
        metadata={"business_id": business.id}
    )
    return customer.id

def create_checkout_session(business: Business, success_url: str, cancel_url: str) -> str:
    """Create a Stripe checkout session for subscription."""
    if not stripe.api_key or settings.STRIPE_SECRET_KEY.startswith("sk_test_"):
        # Test mode - return demo URL
        return f"{settings.APP_URL}/app?demo_payment=true"

    if not business.stripe_customer_id or business.stripe_customer_id == "demo_customer":
        customer_id = create_customer(business)
    else:
        customer_id = business.stripe_customer_id

    try:
        session = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": settings.STRIPE_PRICE_ID, "quantity": 1}],
            mode="subscription",
            success_url=success_url,
            cancel_url=cancel_url,
            metadata={"business_id": business.id}
        )
        return session.url
    except Exception as e:
        # If Stripe fails, return demo URL
        print(f"Stripe error: {e}")
        return f"{settings.APP_URL}/app?demo_payment=true"

def handle_webhook(payload: bytes, sig_header: str, db: Session) -> dict:
    """Handle Stripe webhook events."""
    if not settings.STRIPE_WEBHOOK_SECRET:
        return {"status": "demo"}

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        return {"error": str(e)}

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        biz_id = session["metadata"].get("business_id")
        if biz_id:
            biz = db.query(Business).filter(Business.id == int(biz_id)).first()
            if biz:
                biz.stripe_customer_id = session.get("customer")
                biz.stripe_subscription_id = session.get("subscription")
                biz.subscription_status = "active"
                db.commit()

    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        biz = db.query(Business).filter(Business.stripe_subscription_id == sub["id"]).first()
        if biz:
            biz.subscription_status = "cancelled"
            db.commit()

    elif event["type"] == "invoice.payment_failed":
        invoice = event["data"]["object"]
        biz = db.query(Business).filter(Business.stripe_customer_id == invoice["customer"]).first()
        if biz:
            biz.subscription_status = "past_due"
            db.commit()

    return {"status": "handled", "type": event["type"]}

def is_subscription_active(business: Business) -> bool:
    """Check if business has active access (trial or paid)."""
    if business.subscription_status == "active":
        return True
    if business.subscription_status == "trial":
        if business.trial_ends_at and business.trial_ends_at > datetime.utcnow():
            return True
    return False
