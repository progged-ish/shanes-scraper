# Gmail Setup for Shane's NWS Scraper

Since the military SMTP server (smtp.us.af.mil) is unreachable, here's how to configure the scraper to use Gmail instead.

## Prerequisites

1. You need a Gmail account (you already have progged@gmail.com)
2. You need to generate an App Password for Gmail

## Step 1: Generate Gmail App Password

1. Go to https://myaccount.google.com/
2. Click on "Security" in the left sidebar
3. Under "Signing in to Google", click "App passwords"
4. If prompted, enter your password
5. Select "Mail" as the app and "Other" as the device (or select your device)
6. Click "Generate"
7. Copy the 16-character password that appears

## Step 2: Configure the Script

Edit the `send_dashboard_email_gmail.py` file and update these values:

```python
CONFIG = {
    "from_email": "progged@gmail.com",
    "from_password": "YOUR_16_CHAR_APP_PASSWORD",  # The one you just generated
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    # ... rest of configuration remains the same
}
```

## Step 3: Test the Connection

Run the test script to verify your configuration:

```bash
python3 test_gmail_connection.py
```

## Step 4: Send Your Dashboard

Once the test passes, you can send your dashboard:

```bash
python3 send_dashboard_email_gmail.py
```

## Troubleshooting

If you still get connection errors:

1. Double-check your App Password
2. Ensure 2-Factor Authentication is enabled on your Gmail account
3. Try using a different internet connection (some networks block SMTP ports)
4. Check if your firewall is blocking outgoing connections on port 587

## Security Notes

- Never commit your App Password to version control
- Store sensitive credentials in environment variables for production use
- App Passwords expire if not used for 6 months