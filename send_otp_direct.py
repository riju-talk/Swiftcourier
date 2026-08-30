#!/usr/bin/env python
"""
Pure OTP Email Delivery Test.
Bypasses Celery and Database logic to strictly test SMTP/Inbox delivery.
"""
import os
import sys
import django

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "swiftcourier.settings")
django.setup()

from random import randint
from django.core.mail import EmailMultiAlternatives, get_connection
from django.conf import settings

def test_smtp_connection():
    """Explicitly tests if Django can connect to the SMTP server."""
    print(f"[*] Testing connection to {settings.EMAIL_HOST}:{settings.EMAIL_PORT}...")
    try:
        connection = get_connection()
        connection.open()
        print("[+] SUCCESS: Connected to SMTP server and authenticated!")
        connection.close()
        return True
    except Exception as e:
        print(f"[-] FAILED: Could not connect to SMTP server.")
        print(f"    Error: {e}")
        print("    -> Check EMAIL_HOST, EMAIL_PORT, EMAIL_HOST_USER, and EMAIL_HOST_PASSWORD in settings.py")
        return False

def send_test_email(target_email, target_name):
    """Constructs and sends the actual email."""
    otp = randint(100000, 999999)
    
    subject = "Welcome to IdiotShip! Verify Your Contact Details"
    text_content = f"Hi {target_name},\n\nYour OTP is: {otp}\n\nIf you didn't request this, ignore this email."
    
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6;">
        <h1 style="color:#007BFF;">Welcome to IdiotShip!</h1>
        <p>Hi <strong>{target_name}</strong>,</p>
        <p>Thank you for registering. Please use the following OTP to verify your email:</p>
        <h2 style="color:#007BFF; font-size:32px; letter-spacing:5px; text-align:center; background-color:#f4f4f4; padding:20px; border-radius:5px;">{otp}</h2>
        <p><em>If you didn't attempt to register, please ignore this message.</em></p>
        <p>Best regards,<br><strong>The IdiotShip Team</strong></p>
        <p>This is a test script/p>
    </body>
    </html>
    """

    print(f"\n[*] Sending email to {target_email}...")
    try:
        email = EmailMultiAlternatives(
            subject,
            text_content,
            settings.EMAIL_HOST_USER,
            [target_email],
        )
        email.attach_alternative(html_content, "text/html")
        
        sent_count = email.send(fail_silently=False)
        
        if sent_count > 0:
            print(f"[+] SUCCESS: Email accepted by server! (Generated OTP: {otp})")
            return True
        else:
            print("[-] FAILED: email.send() returned 0 recipients.")
            return False
            
    except Exception as e:
        print(f"[-] FAILED: Error during send process.")
        print(f"    Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("IDIOTSHIP OTP EMAIL DELIVERY TEST")
    print("=" * 60)
    
    # Allow passing email via command line: python script.py test@example.com
    if len(sys.argv) > 1:
        target_email = sys.argv[1]
    else:
        target_email = "fiwep72852@dyleris.com" # Default fallback
        
    target_name = "Test User"
    
    print(f"Target Email : {target_email}")
    print(f"From Email   : {settings.EMAIL_HOST_USER}")
    print(f"SMTP Host    : {settings.EMAIL_HOST}")
    print("=" * 60)
    
    # Step 1: Check if we can even talk to the email server
    if not test_smtp_connection():
        print("\n[-] Aborting test because SMTP connection failed.")
        sys.exit(1)
        
    # Step 2: Send the email
    success = send_test_email(target_email, target_name)
    
    print("\n" + "=" * 60)
    if success:
        print("RESULT: EMAIL SENT SUCCESSFULLY")
        print("\nNext Steps to check Inbox:")
        print("1. Open the inbox for: " + target_email)
        print("2. If it's NOT in the Inbox, check the SPAM/JUNK folder.")
        print("3. If it's in SPAM, your domain needs SPF/DKIM/DMARC records configured.")
    else:
        print("RESULT: EMAIL DELIVERY FAILED")
    print("=" * 60)