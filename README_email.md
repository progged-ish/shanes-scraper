# NWS Dashboard Email Automation

## Quick Start

1. **Update email credentials** in `send_dashboard_email.py`:
   ```python
   FROM_EMAIL = "your-email@25thsqs.af.mil"
   FROM_PASSWORD = "your-password"
   ```

2. **Run once to test:**
   ```bash
   python send_dashboard_email.py
   ```

3. **Automatic daily runs** - Already configured in cron for 0530l daily

## Files

- `send_dashboard_email.py` - Email sender script
- `references/config.example.py` - Configuration template
- `logs/email_*.log` - Daily log files

## Cron Job

Already configured: `0 3 * * *` (daily at 0530l / 0300 UTC)

Job ID: `13f7cef2ed1b`
Next run: 2026-03-31T03:00:00-07:00

## Troubleshooting

Check logs at: `/home/progged-ish/projects/shanes-scraper/logs/`

Common issues:
- Authentication failed: Check FROM_PASSWORD
- SMTP connection failed: Check SMTP_SERVER
- Dashboard missing: Run scraper first
