#!/usr/bin/env python3
"""
Shane's NWS Forecast Discussion Scraper - V3
Two-Stage AI Architecture:
  Stage 1: Extract synoptic features from individual AFDs
  Stage 2: Consolidate all extracted summaries into CONUS-wide outlook
"""

import os
import re
import json
import requests
from bs4 import BeautifulSoup
import datetime
import smtplib
from email.message import EmailMessage

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, 'data')
CONFIG_DIR = os.path.join(BASE_DIR, 'config')

os.makedirs(DATA_DIR, exist_ok=True)

smtp_config_file = os.path.join(CONFIG_DIR, 'smtp_config.json')
smtp_config = None
try:
    with open(smtp_config_file, 'r') as f:
        smtp_config = json.load(f)
except FileNotFoundError:
    print(f"WARNING: Could not find '{smtp_config_file}'. Emailing will be disabled.")


def send_email_with_attachment(filepath):
    """Send the generated text file via email using the loaded SMTP config."""
    if not smtp_config:
        print("Skipping email delivery: SMTP configuration not loaded.")
        return

    try:
        msg = EmailMessage()
        msg['Subject'] = "Shane's Super Top Secret Discussion Scraper V3"
        msg['From'] = smtp_config['sender_email']
        msg['To'] = smtp_config.get('recipient_email', 'channing.weinmeister.1@us.af.mil')
        msg.set_content(f"Attached is the latest NWS Synoptic Summary (V3 - Two-Stage AI).\n\nPlease save the attached .txt file and rename its extension to .html to view it in your browser.")

        with open(filepath, 'rb') as f:
            file_data = f.read()
            file_name = os.path.basename(filepath)

        msg.add_attachment(file_data, maintype='text', subtype='plain', filename=file_name)

        server = smtplib.SMTP(smtp_config['smtp_server'], smtp_config['smtp_port'])
        if smtp_config.get('use_tls', True):
            server.starttls()

        server.login(smtp_config['sender_email'], smtp_config['sender_password'])
        server.send_message(msg)
        server.quit()

        print(f"Successfully emailed {file_name} to {msg['To']}")
    except Exception as e:
        print(f"Failed to send email: {e}")


# --- API Client for LM Studio ---
lm_client = None
lm_model = None

def setup_lm_client():
    """Setup OpenAI-compatible client for LM Studio."""
    from openai import OpenAI
    global lm_client, lm_model
    lm_client = OpenAI(base_url="http://10.0.0.94:1234/v1", api_key="lm-studio")
    lm_model = "gemma-4-e2b-it"
    return lm_client, lm_model


# --- STAGE 1: Extraction Prompt ---
STAGE1_PROMPT = """
You are a Senior Synoptic Meteorologist. Extract ONLY the synoptic-scale features from this AFD.

TASK: Identify and summarize each synoptic-scale feature present in the discussion:
- Frontal Boundaries: Cold, warm, stationary, occluded, or drylines
- Mass Fields: Ridges, troughs (shortwave and longwave), closed upper-level lows/highs
- Air Masses: Arctic boundaries, moisture surges, significant temperature gradients

INSTRUCTIONS:
- For each feature identified, write a 2-4 sentence technical summary of its location, movement, and intensity
- Adjust detail depth based on how much synoptic information is actually present in the AFD
- Do NOT discuss local impacts, meso-scale details, or city forecasts
- Do NOT discuss impacts on specific locations (towns, cities)
- Use ONLY technical meteorological terms
- Output only the extracted features, nothing else

AFD Text:
{afd_text}
""".strip()


def extract_synoptic_features(office_id, afd_text):
    """
    Stage 1: Extract synoptic features from a single AFD.
    Returns a dictionary with extracted features as a list of feature descriptions.
    """
    # Setup LM client if not already done
    global lm_client, lm_model
    if lm_client is None:
        lm_client, lm_model = setup_lm_client()

    # Prepare the prompt with the AFD text
    prompt = STAGE1_PROMPT.replace("{afd_text}", afd_text)

    messages = [
        {"role": "system", "content": "You are a Senior Synoptic Meteorologist. Extract ONLY synoptic-scale features. Be technical, concise, and focus on large-scale patterns."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = lm_client.chat.completions.create(
            model=lm_model,
            messages=messages,
            temperature=0.3,
            stream=False
        )
        ai_summary = response.choices[0].message.content.strip()
        return {
            'office_id': office_id,
            'extracted_summary': ai_summary,
            'raw_afd': afd_text
        }
    except Exception as e:
        print(f"Error extracting features from {office_id}: {e}")
        return {
            'office_id': office_id,
            'extracted_summary': f"Error: {e}",
            'raw_afd': afd_text
        }


# --- STAGE 2: Consolidation Prompt ---
STAGE2_PROMPT = """
You are an expert Lead Forecaster. Below is a collection of synoptic summaries from various NWS offices. Your task is to synthesize these into a single, cohesive CONUS Synoptic Discussion.

Instructions:

De-duplicate: If multiple offices mention the same longwave trough or cold front, combine that information into one entry.
Regional Flow: Organize the summary geographically (e.g., Western US, Plains, Eastern Seaboard) or by feature importance.
Synoptic Narrative: Ensure the final output reads as a continuous narrative of the large-scale atmospheric pattern across the continent.

Input Summaries:
{summaries}

Your consolidated CONUS-wide synoptic outlook:
""".strip()


def consolidate_synoptic_outlook(extracted_data_list):
    """
    Stage 2: Consolidate all Stage 1 extractions into a unified CONUS overview.
    Returns the consolidated text summary.
    """
    global lm_client, lm_model
    if lm_client is None:
        lm_client, lm_model = setup_lm_client()

    # Format all extracted summaries into a single input string
    summaries_text = ""
    for data in extracted_data_list:
        office = data.get('office_id', 'Unknown')
        summary = data.get('extracted_summary', '')
        if summary and summary.strip():
            summaries_text += f"\n\nOffice: {office}\n{summary}\n"

    if not summaries_text.strip():
        return "No synoptic features were identified in the analyzed discussions."

    prompt = STAGE2_PROMPT.replace("{summaries}", summaries_text)

    messages = [
        {"role": "system", "content": "You are an expert Lead Forecaster. Synthesize multiple regional summaries into a unified CONUS-wide outlook. Be concise and focus on coherence."},
        {"role": "user", "content": prompt}
    ]

    try:
        response = lm_client.chat.completions.create(
            model=lm_model,
            messages=messages,
            temperature=0.2,
            stream=False
        )
        consolidated = response.choices[0].message.content.strip()
        return consolidated
    except Exception as e:
        print(f"Error consolidating synoptic outlook: {e}")
        return f"Error consolidating: {e}"


# --- DISCUSSION PARSING ---
OFFICES = {
    'Canada': ['YVR', 'YYC', 'YWG', 'YYZ', 'YUL', 'YHZ'],
    'California': ['EKA', 'MTR', 'STO', 'HNX', 'LOX', 'SGX'],
    'Oregon': ['PQR', 'PDT', 'MFR'],
    'Washington': ['SEW', 'OTX'],
    'Alaska': ['ANC', 'FAI', 'JNU'],
    'Hawaii': ['HFO'],
    'Idaho': ['BOI', 'PIH'],
    'Nevada': ['REV', 'LKN', 'VEF'],
    'Utah': ['SLC'],
    'Arizona': ['FGZ', 'PSR', 'TWC'],
    'Montana': ['TFX', 'GGW', 'BYZ', 'MSO'],
    'Wyoming': ['RIW', 'CYS'],
    'Colorado': ['BOU', 'GJT', 'PUB'],
    'New Mexico': ['ABQ'],
    'North Dakota': ['BIS', 'FGF'],
    'South Dakota': ['ABR', 'FSD', 'UNR'],
    'Nebraska': ['GID', 'LBF', 'OAX'],
    'Kansas': ['DDC', 'GLD', 'ICT', 'TOP'],
    'Oklahoma': ['OUN', 'TSA'],
    'Texas': ['AMA', 'FWD', 'HGX', 'MAF', 'SJT', 'CRP', 'BRO', 'EPZ'],
    'Minnesota': ['DLH', 'MPX', 'FGF'],
    'Iowa': ['DMX', 'DVN', 'ARX'],
    'Missouri': ['EAX', 'LSX', 'SGF'],
    'Arkansas': ['LZK', 'SHV'],
    'Louisiana': ['LIX', 'SHV'],
    'Wisconsin': ['ARX', 'GRB', 'MKX'],
    'Illinois': ['ILX', 'LOT', 'LSX'],
    'Michigan': ['APX', 'DTX', 'GRR', 'MQT'],
    'Indiana': ['IND', 'IWX', 'LMK'],
    'Ohio': ['CLE', 'ILN', 'PBZ'],
    'Kentucky': ['JKL', 'LMK', 'PAH'],
    'Tennessee': ['OHX', 'MRX', 'MEG'],
    'West Virginia': ['LWX', 'CBW'],
    'Pennsylvania': ['AKQ', 'CTP', 'GSP', 'LWX', 'OKX', 'PBZ', 'PHI', 'RAH', 'RMX', 'DTX', 'DTR', 'LBF', 'VFF'],
    'New Jersey': ['OKX', 'PBZ'],
    'New York': ['BGM', 'BTV', 'ALY', 'GYO', 'OKX', 'PBZ', 'LIX'],
    'Vermont': ['BTV', 'ALY', 'GYO'],
    'Virginia': ['AKQ', 'LWX', 'RAH'],
    'Maryland': ['AKQ', 'LWX', 'LIX'],
    'Massachusetts': ['BOX', 'MPX', 'LWX'],
    'Connecticut': ['BOX', 'OKX'],
    'Rhode Island': ['BOX', 'OKX'],
    'North Carolina':['FFX', 'CHS', 'GSP', 'LIX', 'LWX', 'OHX'],
    'South Carolina': ['CHS', 'GSP', 'OHX'],
    'Georgia': ['JAX', 'CHS', 'GSP', 'LWX'],
    'Florida': ['EYW', 'SRX', 'TBW', 'MLB', 'TBW'],
    'Alabama': ['MOB', 'BTX', 'GSP', 'LIX'],
    'Mississippi': ['BTX', 'JAN', 'LIX'],
    'Tennessee': ['OHX', 'MEG', 'LIX'],
}

ALL_OFFICES_SYNoptic = []
for region, offices in OFFICES.items():
    ALL_OFFICES_SYNoptic.extend(offices)


def get_forecast_discussion(office_id):
    """Fetch the forecast discussion text for a given NWS office."""
    url = f"https://forecast.weather.gov/product.php?site={office_id.upper()}&issuedby={office_id.upper()}&product=AFD&format=txt&version=1&glossary=0"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        preformatted_text = soup.find('pre')
        if preformatted_text:
            text = preformatted_text.get_text().strip()
            # Extract the SYNOPTIC DISCUSSION section only
            synoptic_match = re.search(r'SYNOPTIC\s+DISCUSSION.*?(?=^\w|\Z)', text, re.IGNORECASE | re.MULTILINE | re.DOTALL)
            if synoptic_match:
                return synoptic_match.group(0).strip()
            # Fallback: return full discussion if SYNOPTIC section not found
            return text
        return ""
    except Exception as e:
        print(f"Error fetching discussion for {office_id}: {e}")
        return ""


def main():
    """Main function - runs V3 two-stage AI extraction."""
    script_version = "3.0.0 (Two-Stage AI Synoptic)"
    execution_start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    print(f"Starting Shane's V3 Synoptic Scraper {script_version}")
    print(f"Execution started at: {execution_start}")

    # --- STAGE 1: Extract from all offices ---
    print("\n=== STAGE 1: Extracting Synoptic Features ===")
    extracted_data = []

    for office_id in sorted(set(ALL_OFFICES_SYNoptic)):
        print(f"Processing {office_id}...", end=" ", flush=True)
        afd_text = get_forecast_discussion(office_id)
        if afd_text:
            result = extract_synoptic_features(office_id, afd_text)
            extracted_data.append(result)
            print(f"Extracted {len(result.get('extracted_summary', '').split())} words")
        else:
            print("No discussion found")

    # --- STAGE 2: Consolidate into CONUS outlook ---
    print("\n=== STAGE 2: Consolidating CONUS Outlook ===")
    print("Sending to AI for synthesis...")
    conus_outlook = consolidate_synoptic_outlook(extracted_data)

    print(f"\nConsolidated outlook ({len(conus_outlook)} chars):")
    print(conus_outlook[:500] + "..." if len(conus_outlook) > 500 else conus_outlook)

    # --- BUILD HTML OUTPUT ---
    content_pane_html = (
        f"<h1>Shane's Super Top Secret Discussion Scraper V3</h1>"
        f"<p>Two-Stage AI Architecture: Stage 1 (Extract) + Stage 2 (Consolidate)</p>"
        f"<p><strong>Execution Time:</strong> {execution_start} | <strong> offices processed:</strong> {len(extracted_data)}</p>"
        f"<h2>CONUS Synoptic Outlook (AI-Generated Consolidation)</h2>"
        f"<div style='font-family: -apple-system, BlinkMacSystemFont, \"Segoe UI\", Roboto, sans-serif; padding: 20px; background: #ffffff; border: 1px solid #ddd; border-radius: 8px;'>"
    )

    # Add AI-generated CONUS outlook - plain text, no HTML escaping needed
    content_pane_html += f"<pre style='white-space: pre-wrap; word-wrap: break-word; font-size: 14px; line-height: 1.6;'>{conus_outlook}</pre>"

    content_pane_html += "</div>"

    final_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>Shane's Super Top Secret Discussion Scraper V3</title>
    <style>
        body, html {{ margin: 0; padding: 20px; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        h1 {{ color: #333; margin-bottom: 20px; }}
        h2 {{ color: #444; margin-top: 30px; }}
        h3 {{ color: #555; margin: 15px 0; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; background: #f8f8f8; padding: 15px; border-radius: 4px; border: 1px solid #ddd; }}
        a {{ color: #0066cc; }}
    </style>
</head>
<body>
    {content_pane_html}
</body>
</html>
"""

    # --- Save Output ---
    output_filename = os.path.join(DATA_DIR, "Shane_Synoptic_Summary.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_html)

    print(f"\nSuccessfully saved to {output_filename}")

    # Send email
    send_email_with_attachment(output_filename)


if __name__ == '__main__':
    main()
