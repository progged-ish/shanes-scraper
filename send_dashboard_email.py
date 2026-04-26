#!/usr/bin/env python3
"""
NWS Dashboard Email Sender
Sends the dashboard HTML file to specified recipients via SMTP.

Author: progged-ish (25th Operational Weather Squadron)
"""

import os
import sys
import time
import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from datetime import datetime
from pathlib import Path

# Configuration — loaded from environment variables
CONFIG = {
    "from_email": os.environ.get("SMTP_FROM_EMAIL", ""),
    "from_password": os.environ.get("SMTP_FROM_PASSWORD", ""),
    "smtp_server": os.environ.get("SMTP_SERVER", "smtp.us.af.mil"),
    "smtp_port": int(os.environ.get("SMTP_PORT", "587")),
    "recipients": [r.strip() for r in os.environ.get("SMTP_TO_EMAIL", "").split(",") if r.strip()],
    "subject": os.environ.get("SMTP_SUBJECT", "NWS Discussion Dashboard - Daily"),
    "dashboard_path": os.environ.get("DASHBOARD_PATH", "/home/progged-ish/projects/shanes-scraper/data/shanes_nws_dashboard_v2.html"),
    "max_retries": int(os.environ.get("SMTP_MAX_RETRIES", "3")),
    "retry_delay": int(os.environ.get("SMTP_RETRY_DELAY", "300")),
}

# Logging setup
LOG_DIR = Path("/home/progged-ish/projects/shanes-scraper/logs")
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / f"email_{datetime.now().strftime('%Y-%m-%d')}.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


def check_dashboard_exists():
    """Verify the dashboard file exists."""
    dashboard_path = Path(CONFIG["dashboard_path"])
    if not dashboard_path.exists():
        logger.error(f"Dashboard file not found: {dashboard_path}")
        return False
    
    if dashboard_path.stat().st_size == 0:
        logger.error(f"Dashboard file is empty: {dashboard_path}")
        return False
    
    logger.info(f"Dashboard file found: {dashboard_path} ({dashboard_path.stat().st_size / 1024:.1f} KB)")
    return True


def get_email_config():
    """Validate email configuration."""
    if not CONFIG["from_email"]:
        logger.error("FROM_EMAIL not configured")
        return False
    
    if not CONFIG["from_password"]:
        logger.error("FROM_PASSWORD not configured")
        return False
    
    if not CONFIG["smtp_server"]:
        logger.error("SMTP_SERVER not configured")
        return False
    
    return True


def send_email_with_attachments():
    """Send the dashboard file as email attachment."""
    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = CONFIG["from_email"]
        msg["To"] = ", ".join(CONFIG["recipients"])
        msg["Subject"] = f"{CONFIG['subject']} - {datetime.now().strftime('%Y-%m-%d')}"
        
        # Add body
        body = f"""
Dear Channing,

Please find attached today's NWS Discussion Dashboard for all 119 forecast offices.

The dashboard includes:
- Interactive map of all forecast offices
- AI-generated summaries for each office
- Keyword extraction and analysis
- Full forecast discussion text

To view: Save the attached HTML file and open in any web browser.

Best regards,
progged-ish
25th Operational Weather Squadron
        """
        msg.attach(MIMEText(body, "plain"))
        
        # Add dashboard as attachment
        dashboard_path = Path(CONFIG["dashboard_path"])
        with open(dashboard_path, "rb") as f:
            attachment = MIMEApplication(f.read(), Name=os.path.basename(dashboard_path))
        attachment["Content-Disposition"] = f'attachment; filename="{dashboard_path.name}"'
        msg.attach(attachment)
        
        # Connect and send
        server = smtplib.SMTP(CONFIG["smtp_server"], CONFIG["smtp_port"], timeout=30)
        server.starttls()
        server.login(CONFIG["from_email"], CONFIG["from_password"])
        
        logger.info(f"Sending to {len(CONFIG['recipients'])} recipient(s)...")
        server.send_message(msg)
        server.quit()
        
        logger.info("✓ Email sent successfully!")
        return True
        
    except smtplib.SMTPAuthenticationError:
        logger.error("✗ SMTP Authentication failed. Check credentials.")
        return False
    except smtplib.SMTPConnectError:
        logger.error(f"✗ SMTP Connection failed. Server: {CONFIG['smtp_server']}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"✗ SMTP Error: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error: {type(e).__name__}: {e}")
        return False


def send_failure_notification():
    """Send failure notification email."""
    try:
        msg = MIMEMultipart()
        msg["From"] = CONFIG["from_email"]
        msg["To"] = "progged-ish@25thsqs.af.mil"  # Send to yourself
        msg["Subject"] = f"ALERT: Dashboard Email Failed - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        
        body = f"""
ALERT: NWS Dashboard Email Failed

Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Error Log: {LOG_FILE}

Please check the log file for details and verify your SMTP credentials.

Best regards,
Auto-Alert System
        """
        msg.attach(MIMEText(body, "plain"))
        
        server = smtplib.SMTP(CONFIG["smtp_server"], CONFIG["smtp_port"], timeout=30)
        server.starttls()
        server.login(CONFIG["from_email"], CONFIG["from_password"])
        server.send_message(msg)
        server.quit()
        
        logger.warning("✓ Failure notification sent")
        
    except Exception as e:
        logger.error(f"Failed to send failure notification: {e}")


def retry_logic(attempt=1):
    """Execute with retry logic."""
    success = False
    
    for attempt in range(1, CONFIG["max_retries"] + 1):
        logger.info(f"Attempt {attempt}/{CONFIG['max_retries']}")
        
        if send_email_with_attachments():
            success = True
            break
        
        if attempt < CONFIG["max_retries"]:
            logger.info(f"Waiting {CONFIG['retry_delay']} seconds before retry...")
            time.sleep(CONFIG["retry_delay"])
    
    return success


def main():
    """Main execution function."""
    print("=" * 60)
    print("NWS Dashboard Email Sender")
    print("=" * 60)
    print(f"\n📁 Dashboard: {CONFIG['dashboard_path']}")
    print(f"📧 From: {CONFIG['from_email']}")
    print(f"📧 To: {', '.join(CONFIG['recipients'])}")
    print(f"🌐 SMTP: {CONFIG['smtp_server']}:{CONFIG['smtp_port']}")
    print()
    
    # Validate prerequisites
    if not check_dashboard_exists():
        logger.error("Aborted: Dashboard file missing or invalid")
        sys.exit(1)
    
    if not get_email_config():
        logger.error("Aborted: Email configuration incomplete")
        sys.exit(1)
    
    logger.info("Starting email send process...")
    
    # Execute with retries
    success = retry_logic()
    
    if success:
        print("\n✓ Email sent successfully!")
        sys.exit(0)
    else:
        print("\n✗ Email failed after all retries")
        logger.error("Final failure - sending notification")
        send_failure_notification()
        sys.exit(1)


if __name__ == "__main__":
    main()
