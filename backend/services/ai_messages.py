import httpx
import json
from backend.core.config import settings

SYSTEM_PROMPT = """You are a friendly appointment reminder assistant for small businesses.
Generate short, professional, warm SMS reminder messages.
Keep messages under 160 characters when possible.
Always include the business name, client name, date/time, and service.
Be friendly but concise. Do NOT add quotes or extra formatting."""

def generate_reminder_message(
    business_name: str,
    business_type: str,
    client_name: str,
    service: str,
    scheduled_at: str,
    reminder_type: str = "24h",
    custom_base: str = None
) -> str:
    """Generate a personalized AI reminder message using local Ollama."""

    if reminder_type == "24h":
        timing = "tomorrow"
    else:
        timing = "in 2 hours"

    if custom_base:
        prompt = f"""Rewrite this appointment reminder to sound more personalized and friendly, keeping it under 160 chars:
Base message: {custom_base}
Client: {client_name}, Service: {service}, Time: {timing}"""
    else:
        prompt = f"""Write a brief SMS appointment reminder for:
Business: {business_name} ({business_type})
Client first name: {client_name.split()[0]}
Service: {service or 'appointment'}
Time: {scheduled_at} ({timing})

Make it friendly, personal, and under 160 characters. Include a way to confirm or cancel."""

    try:
        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={
                "model": settings.OLLAMA_MODEL,
                "prompt": f"{SYSTEM_PROMPT}\n\n{prompt}",
                "stream": False,
                "options": {"temperature": 0.7, "num_predict": 100}
            },
            timeout=30.0
        )
        if response.status_code == 200:
            result = response.json()
            msg = result.get("response", "").strip()
            # Clean up any quotes
            msg = msg.strip('"\'')
            return msg[:320]  # SMS safe limit
    except Exception as e:
        print(f"Ollama error: {e}")

    # Fallback message if Ollama is down
    first_name = client_name.split()[0]
    return (
        f"Hi {first_name}! Reminder: your {service or 'appointment'} at {business_name} "
        f"is {timing} at {scheduled_at}. Reply CONFIRM or CANCEL."
    )

def generate_followup_message(business_name: str, client_name: str) -> str:
    """Generate a post no-show follow-up message."""
    first_name = client_name.split()[0]
    try:
        prompt = f"Write a short, friendly SMS to {first_name} who missed their appointment at {business_name}. Offer to reschedule. Under 160 chars."
        response = httpx.post(
            f"{settings.OLLAMA_URL}/api/generate",
            json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False,
                  "options": {"temperature": 0.7, "num_predict": 80}},
            timeout=20.0
        )
        if response.status_code == 200:
            return response.json().get("response", "").strip().strip('"\'')[:320]
    except:
        pass
    return f"Hi {first_name}, we missed you today at {business_name}! Would you like to reschedule? Reply or call us."
