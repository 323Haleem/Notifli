import httpx
import json
from backend.core.config import settings

SYSTEM_PROMPT = """You are a friendly appointment reminder assistant for small businesses.
Generate short, professional, warm SMS reminder messages.
Keep messages under 160 characters when possible.
Always include the business name, client name, date/time, and service.
Be friendly but concise. Do NOT add quotes or extra formatting."""

def _call_openrouter(prompt: str, max_tokens: int = 100) -> str:
    """Call OpenRouter API for message generation."""
    if not settings.OPENROUTER_API_KEY:
        return ""
    
    try:
        response = httpx.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": settings.APP_URL,
                "X-Title": settings.APP_NAME,
            },
            json={
                "model": "openai/gpt-4o-mini",  # Cheap, fast, good for short messages
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": 0.7,
            },
            timeout=15.0
        )
        if response.status_code == 200:
            result = response.json()
            return result.get("choices", [{}])[0].get("message", {}).get("content", "").strip().strip('"\'')
    except Exception as e:
        print(f"OpenRouter error: {e}")
    
    return ""

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

    # Try OpenRouter first (for production), fallback to Ollama (local dev), then hardcoded fallback
    ai_message = ""
    
    # Attempt OpenRouter if API key is set
    if settings.OPENROUTER_API_KEY:
        ai_message = _call_openrouter(prompt, max_tokens=100)
    
    # Fallback to local Ollama if OpenRouter failed or not configured
    if not ai_message and settings.OLLAMA_URL:
        try:
            response = httpx.post(
                f"{settings.OLLAMA_URL}/api/generate",
                json={
                    "model": settings.OLLAMA_MODEL,
                    "prompt": f"{SYSTEM_PROMPT}\\n\\n{prompt}",
                    "stream": False,
                    "options": {"temperature": 0.7, "num_predict": 100}
                },
                timeout=10.0  # Shorter timeout for Ollama
            )
            if response.status_code == 200:
                result = response.json()
                ai_message = result.get("response", "").strip().strip('"').strip("'")
        except Exception as e:
            print(f"Ollama error (expected in production): {e}")
    
    # Return AI message if generated, otherwise use fallback
    if ai_message:
        return ai_message[:320]  # SMS safe limit

    # Fallback message if Ollama is down
    first_name = client_name.split()[0]
    return (
        f"Hi {first_name}! Reminder: your {service or 'appointment'} at {business_name} "
        f"is {timing} at {scheduled_at}. Reply CONFIRM or CANCEL."
    )

def generate_followup_message(business_name: str, client_name: str) -> str:
    """Generate a post no-show follow-up message."""
    first_name = client_name.split()[0]
    prompt = f"Write a short, friendly SMS to {first_name} who missed their appointment at {business_name}. Offer to reschedule. Under 160 chars."
    
    ai_message = ""
    
    # Try OpenRouter first
    if settings.OPENROUTER_API_KEY:
        ai_message = _call_openrouter(prompt, max_tokens=80)
    
    # Fallback to Ollama
    if not ai_message and settings.OLLAMA_URL:
        try:
            response = httpx.post(
                f"{settings.OLLAMA_URL}/api/generate",
                json={"model": settings.OLLAMA_MODEL, "prompt": prompt, "stream": False,
                      "options": {"temperature": 0.7, "num_predict": 80}},
                timeout=10.0
            )
            if response.status_code == 200:
                ai_message = response.json().get("response", "").strip().strip('"').strip("'")[:320]
        except:
            pass
    
    if ai_message:
        return ai_message
    
    # Hardcoded fallback
    return f"Hi {first_name}, we missed you today at {business_name}! Would you like to reschedule? Reply or call us."
