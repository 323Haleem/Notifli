#!/usr/bin/env python3
"""
Twilio SMS Test Script for Notifli
Tests SMS delivery capability before going live.

Usage:
    python3 test_sms.py [your_phone_number]
    
Example:
    python3 test_sms.py +1234567890
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Check for twilio
try:
    from twilio.rest import Client
except ImportError:
    print("❌ Twilio library not installed!")
    print("   Run: pip install twilio")
    sys.exit(1)

def get_twilio_credentials():
    """Load Twilio credentials from environment."""
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    twilio_number = os.getenv("TWILIO_PHONE_NUMBER")
    
    if not account_sid:
        print("❌ TWILIO_ACCOUNT_SID not found in .env")
        return None, None, None
    
    if not auth_token:
        print("❌ TWILIO_AUTH_TOKEN not found in .env")
        return None, None, None
    
    if not twilio_number:
        print("❌ TWILIO_PHONE_NUMBER not found in .env")
        return None, None, None
    
    return account_sid, auth_token, twilio_number

def send_test_sms(to_number: str, message: str = "Test message from Notifli!") -> bool:
    """Send a test SMS and return success status."""
    account_sid, auth_token, twilio_number = get_twilio_credentials()
    
    if not all([account_sid, auth_token, twilio_number]):
        return False
    
    print(f"\n📱 Twilio SMS Test")
    print(f"   From: {twilio_number}")
    print(f"   To: {to_number}")
    print(f"   Message: {message}")
    print("-" * 60)
    
    try:
        # Initialize Twilio client
        client = Client(account_sid, auth_token)
        
        # Send the message
        print("⏳ Sending SMS...")
        message = client.messages.create(
            body=message,
            from_=twilio_number,
            to=to_number
        )
        
        # Check status
        print(f"\n✅ SMS sent successfully!")
        print(f"   Message SID: {message.sid}")
        print(f"   Status: {message.status}")
        print(f"   Date Created: {message.date_created}")
        
        # Fetch latest status
        fetched_message = client.messages(message.sid).fetch()
        print(f"   Current Status: {fetched_message.status}")
        
        if fetched_message.status in ['sent', 'delivered']:
            print(f"\n🎉 SUCCESS! SMS delivery confirmed.")
            return True
        else:
            print(f"\n⚠️  SMS sent but status is: {fetched_message.status}")
            return True
            
    except Exception as e:
        print(f"\n❌ FAILED to send SMS!")
        print(f"   Error: {str(e)}")
        
        # Common error handling
        error_msg = str(e).lower()
        if "account" in error_msg and "suspended" in error_msg:
            print(f"\n⚠️  Your Twilio account may be suspended or restricted.")
            print(f"   Check: https://console.twilio.com")
        elif "unverified" in error_msg:
            print(f"\n⚠️  Your Twilio number needs verification.")
            print(f"   In test mode, you can only send to verified numbers.")
            print(f"   Upgrade to production mode or verify the recipient number.")
        elif "a2p" in error_msg or "10dlc" in error_msg:
            print(f"\n⚠️  A2P 10DLC registration may be required.")
            print(f"   Visit: https://console.twilio.com/a2p")
        elif "invalid" in error_msg and "phone" in error_msg:
            print(f"\n⚠️  Invalid phone number format.")
            print(f"   Use E.164 format: +1234567890")
        
        return False

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python3 test_sms.py [phone_number]")
        print("Example: python3 test_sms.py +1234567890")
        print("\nThis will send a test SMS to verify Twilio is working.")
        sys.exit(1)
    
    phone_number = sys.argv[1]
    
    # Validate phone number format
    if not phone_number.startswith("+"):
        print("⚠️  Phone number should start with + (E.164 format)")
        print("   Example: +1234567890")
        response = input("Continue anyway? (y/n): ")
        if response.lower() != 'y':
            sys.exit(0)
    
    # Send test SMS
    success = send_test_sms(phone_number)
    
    if success:
        print("\n✅ Twilio SMS test PASSED!")
        sys.exit(0)
    else:
        print("\n❌ Twilio SMS test FAILED!")
        print("\nTroubleshooting steps:")
        print("1. Check Twilio credentials in .env file")
        print("2. Verify Twilio account is active: https://console.twilio.com")
        print("3. In test mode, recipient must be a verified number")
        print("4. For production, complete A2P 10DLC registration")
        sys.exit(1)

if __name__ == "__main__":
    main()
