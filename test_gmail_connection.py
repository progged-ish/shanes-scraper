#!/usr/bin/env python3
"""
Test script to verify Gmail SMTP connection for Shane's NWS Scraper
"""

import smtplib
from email.mime.text import MIMEText

def test_gmail_connection(email, app_password):
    """Test Gmail SMTP connection"""
    try:
        print("Testing Gmail SMTP connection...")
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(email, app_password)
        print("✓ Successfully connected to Gmail SMTP!")
        server.quit()
        return True
    except Exception as e:
        print(f"✗ Failed to connect to Gmail SMTP: {e}")
        return False

if __name__ == "__main__":
    # You'll need to replace these with actual credentials
    email = "progged@gmail.com"
    app_password = "YOUR_GMAIL_APP_PASSWORD"  # Generate at https://myaccount.google.com/apppasswords
    
    print("Gmail SMTP Test for Shane's NWS Scraper")
    print("=" * 40)
    
    if test_gmail_connection(email, app_password):
        print("\nYou're ready to send emails via Gmail!")
        print("Next steps:")
        print("1. Update the send_dashboard_email_gmail.py script with your actual credentials")
        print("2. Run the script to send your dashboard")
    else:
        print("\nConnection failed. Please check:")
        print("- Your Gmail address is correct")
        print("- You've generated an App Password at https://myaccount.google.com/apppasswords")
        print("- Your App Password is entered correctly")