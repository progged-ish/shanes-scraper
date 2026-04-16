import requests
from bs4 import BeautifulSoup
import re
import base64
from collections import defaultdict
import datetime
import html
import os
import sys
import json
import smtplib
from email.message import EmailMessage

# --- LM Studio Configuration for GEMMA-4 Fast Model ---
from openai import OpenAI
import socket

# Set a 60-second timeout for API calls
socket.setdefaulttimeout(60)

# Local LM Studio instance running GEMMA-4
lm_client = OpenAI(
    base_url="http://10.0.0.94:1234/v1",
    api_key="***",
    timeout=60
)

FAST_MODEL = "gemma-4-e2b-it"

def call_fast_model(messages, model=FAST_MODEL, temperature=0.3):
    """
    Call GEMMA-4 via local LM Studio for fast summarization.
    Uses OpenAI-compatible API format.
    """
    response = lm_client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        stream=False
    )
    return {
        "choices": [{"message": {"content": choice.message.content}} for choice in response.choices]
    }


def summarize_features(discussion_text, keywords):
    """Summarizes features based on a list of keywords."""
    summary, keyword_counts, found_sentences = [], defaultdict(int), set()
    sentences = re.split(r'(?<=[.!?])\s+', discussion_text.replace('\n', ' '))
    for sentence in sentences:
        found_keywords = [k for k in keywords if re.search(r'\b' + re.escape(k) + r'\b', sentence, re.IGNORECASE)]
        if found_keywords:
            cleaned_sentence = sentence.strip()
            if cleaned_sentence not in found_sentences:
                summary.append(f"- {cleaned_sentence}")
                found_sentences.add(cleaned_sentence)
            for keyword in found_keywords:
                keyword_counts[keyword.lower()] += 1
    return summary, keyword_counts


def extract_synoptic_discussion(text: str) -> str:
    """
    Extract only the Synoptic Discussion section from an NWS AFD.
    
    Args:
        text: Full Area Forecast Discussion text
        
    Returns:
        Only the SYNOPTIC section content, or full text if not found
    """
    if not text or text.strip() == "":
        return text
    
    lines = text.split('\n')
    synoptic_start = None
    synoptic_end = None
    
    for i, line in enumerate(lines):
        clean_line = line.upper().replace('DISCUSSION', '').replace(':', '').strip()
        clean_line = clean_line.replace(' ', '').replace('-', '').replace('_', '')
        
        if 'SYNOPS' in clean_line and len(clean_line) < 15:
            synoptic_start = i
            break
    
    if synoptic_start is None:
        for i, line in enumerate(lines):
            line_upper = line.strip().upper()
            if line_upper.startswith('SYNOPS') or 'SYNOPTIC' in line_upper:
                synoptic_start = i
                break
    
    if synoptic_start is None:
        return text
    
    major_headers = ['DISCUSSION', 'IMAGERY', 'NEXT FEW HOURS', 'FORECAST',
                    'AVIATION', 'MARINE', 'COASTAL', 'INLAND', 'LAKES']
    
    for i in range(synoptic_start + 1, len(lines)):
        line_upper = lines[i].upper().strip()
        for header in major_headers:
            if header in line_upper and len(line_upper) < 100:
                synoptic_end = i
                break
        if synoptic_end:
            break
    
    if synoptic_end is None:
        synoptic_end = len(lines)
    
    synoptic_lines = lines[synoptic_start:synoptic_end]
    
    if len(synoptic_lines) < 2:
        return text
    
    return '\n'.join(synoptic_lines)


# --- Paths Setup & Email Config ---
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
        msg['Subject'] = "Shane's Super Top Secret Discussion Scraper"
        msg['From'] = smtp_config['sender_email']
        msg['To'] = smtp_config.get('recipient_email', 'channing.weinmeister.1@us.af.mil')
        msg.set_content(f"Attached is the latest NWS Synoptic Summary.\n\nPlease save the attached .txt file and rename its extension to .html to view it in your browser.")

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


# --- FUNCTIONS ---

def get_forecast_discussion(office_id):
    """Fetches the forecast discussion text for a given NWS office."""
    url = f"https://forecast.weather.gov/product.php?site={office_id.upper()}&issuedby={office_id.upper()}&product=AFD&format=txt&version=1&glossary=0"
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        preformatted_text = soup.find('pre')
        return (preformatted_text.get_text(), url) if preformatted_text else (f"Could not find forecast discussion text for {office_id.upper()}.", url)
    except requests.exceptions.RequestException as e:
        return f"Error fetching data for {office_id.upper()}: {str(e)}", url

def get_ai_summary(text: str) -> str:
    """
    Generate AI-powered summary using minimax-m2.5 via Ollama Cloud Pro.
    
    Routes to the fast model for quick summarization.
    Only passes the Synoptic Discussion portion to the AI model.
    
    Args:
        text: Forecast discussion text
        
    Returns:
        AI-generated summary string (3-4 bullets from Synoptic section)
    """
    # Extract only Synoptic Discussion for summarization (CRITICAL - only pass synoptic text)
    synoptic_text = extract_synoptic_discussion(text)
    
    if not synoptic_text:
        return "[No content to summarize]"
    
    try:
        response_data = call_fast_model(
            messages=[
                {"role": "system", "content": "You are an expert at concise, accurate summarization."},
                {"role": "user", "content": f"Summarize this in 3-4 bullet points:\n\n{synoptic_text}"}
            ],
            temperature=0.3
        )

        if "choices" in response_data and len(response_data["choices"]) > 0:
            message = response_data["choices"][0]["message"]
            if "content" in message:
                return message["content"].strip()
    except Exception as e:
        # Ollama Cloud Pro unavailable or failed - fallback to minimal summary
        return generate_minimal_summary(synoptic_text)

def generate_minimal_summary(synoptic_text: str) -> str:
    """Generate a simple keyword-based summary if AI fails."""
    summary_lines = ["- Weather pattern analysis from NWS forecast discussion"]
    
    # Extract key info from synoptic text
    lines = synoptic_text.split('\n')
    for line in lines:
        line = line.strip()
        if 'trough' in line.lower() or 'ridge' in line.lower():
            summary_lines.append(f"- {line[:80]}...")
        elif 'front' in line.lower():
            summary_lines.append(f"- {line[:80]}...")
    
    return "\n".join(summary_lines[:4]) if len(summary_lines) > 1 else "[Unable to generate summary]"

def highlight_keywords(text, color_map):
    """Applies colored span tags to keywords in a text string. Preserves <br> tags."""
    # Split by <br> to preserve actual line breaks in output
    sections = text.split('<br>')
    processed_sections = []
    for section in sections:
        # Escape the section first
        escaped_section = html.escape(section)
        sorted_keywords = sorted(color_map.keys(), key=len, reverse=True)
        for keyword in sorted_keywords:
            color = color_map[keyword]
            escaped_section = re.sub(
                r'\b' + re.escape(keyword) + r'\b',
                lambda m: f'<span style="background-color:{color}; font-weight:bold; padding: 2px 0; border-radius: 3px;">{m.group(0)}</span>',
                escaped_section,
                flags=re.IGNORECASE
            )
        processed_sections.append(escaped_section)
    # Rejoin with actual <br> tags
    return '<br>'.join(processed_sections)


# --- JSON Cache Helpers ---
def load_office_cache(office_id, cache_dir="data/office_cache"):
    """Load cached extraction for an office, return None if not cached."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{office_id}.json")
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r") as f:
                return json.load(f)
        except:
            return None
    return None

def save_office_cache(office_id, data, cache_dir="data/office_cache"):
    """Save extraction data to cache file."""
    os.makedirs(cache_dir, exist_ok=True)
    cache_file = os.path.join(cache_dir, f"{office_id}.json")
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2)


def main():
    """Main function to scrape, analyze, and summarize NWS forecast discussions."""
    script_version = "4.0.0"
    execution_time_start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    print(f"Starting Shane's Super Top Secret Discussion Scraper {script_version}")
    print(f"Execution started at: {execution_time_start}")
    
    # --- DATA DICTIONARIES ---
    all_offices_synoptic = {
        'Canada': ['YVR', 'YYC', 'YWG', 'YYZ', 'YUL', 'YHZ'],
        'California': ['EKA', 'MTR', 'STO', 'HNX', 'LOX', 'SGX'], 'Oregon': ['PQR', 'PDT', 'MFR'], 'Washington': ['SEW', 'OTX'],
        'Alaska': ['ANC', 'FAI', 'JNU'], 'Hawaii': ['HFO'], 'Idaho': ['BOI', 'PIH'], 'Nevada': ['REV', 'LKN', 'VEF'], 'Utah': ['SLC'],
        'Arizona': ['FGZ', 'PSR', 'TWC'], 'Montana': ['TFX', 'GGW', 'BYZ', 'MSO'], 'Wyoming': ['RIW', 'CYS'], 'Colorado': ['BOU', 'GJT', 'PUB'],
        'New Mexico': ['ABQ'], 'North Dakota': ['BIS', 'FGF'], 'South Dakota': ['ABR', 'FSD', 'UNR'], 'Nebraska': ['GID', 'LBF', 'OAX'],
        'Kansas': ['DDC', 'GLD', 'ICT', 'TOP'], 'Oklahoma': ['OUN', 'TSA'], 'Texas': ['AMA', 'FWD', 'HGX', 'MAF', 'SJT', 'CRP', 'BRO', 'EPZ'],
        'Minnesota': ['DLH', 'MPX', 'FGF'], 'Iowa': ['DMX', 'DVN', 'ARX'], 'Missouri': ['EAX', 'LSX', 'SGF'], 'Arkansas': ['LZK', 'SHV'],
        'Louisiana': ['LIX', 'SHV'], 'Wisconsin': ['ARX', 'GRB', 'MKX'], 'Illinois': ['ILX', 'LOT', 'LSX'], 'Michigan': ['APX', 'DTX', 'GRR', 'MQT'],
        'Indiana': ['IND', 'IWX', 'LMK'], 'Ohio': ['CLE', 'ILN', 'PBZ'], 'Kentucky': ['JKL', 'LMK', 'PAH'], 'Tennessee': ['OHX', 'MRX', 'MEG'],
        'Mississippi': ['JAN', 'MEG'], 'Alabama': ['BMX', 'HUN', 'MOB'], 'Florida': ['JAX', 'KEY', 'MFL', 'MLB', 'TAE', 'TBW'],
        'Georgia': ['FFC', 'JAX', 'TAE'], 'South Carolina': ['CHS', 'GSP', 'CAE', 'ILM'], 'North Carolina': ['RAH', 'GSP', 'MHX', 'ILM', 'RNK'],
        'Virginia': ['AKQ', 'LWX', 'RNK'], 'West Virginia': ['RLX', 'LWX', 'PBZ'], 'Pennsylvania': ['CTP', 'PHI', 'PBZ'], 'New Jersey': ['PHI', 'OKX'],
        'Delaware': ['PHI'], 'Maryland': ['LWX'], 'New York': ['ALY', 'BUF', 'BGM', 'OKX'], 'Connecticut': ['BOX', 'OKX'], 'Rhode Island': ['BOX'],
        'Massachusetts': ['BOX'], 'Vermont': ['BTV', 'ALY'], 'New Hampshire': ['GYX', 'BOX'], 'Maine': ['GYX', 'CAR']
    }
    state_abbreviations = {'Canada': 'CAN', 'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'}
    
    all_keywords = ['front', 'fronts', 'trough', 'troughs', 'dry line', 'dryline', 'ridge', 'shortwave', 'jet streak', 'surface low', 'upper low', 'record high', 'record low', 'record precipitation', 'record snowfall', 'arctic']
    keyword_colors = {'front': '#FFADAD', 'fronts': '#FFADAD', 'trough': '#FFD6A5', 'troughs': '#FFD6A5', 'shortwave': '#FFD6A5', 'dry line': '#FDFFB6', 'dryline': '#FDFFB6', 'ridge': '#CAFFBF', 'jet streak': '#9BF6FF', 'surface low': '#A0C4FF', 'upper low': '#A0C4FF', 'record high': '#ffcccb', 'record low': '#add8e6', 'record precipitation': '#90ee90', 'record snowfall': '#d3d3d3', 'arctic': '#ADD8E6'}
    processed_data, keyword_counts, keyword_map = defaultdict(dict), defaultdict(int), defaultdict(lambda: defaultdict(list))

    # --- Data Processing Loop ---
    for state, offices in all_offices_synoptic.items():
        for office in offices:
            print(f"Fetching discussion for {office.upper()}...")
            discussion, url = get_forecast_discussion(office)
            synoptic_text = extract_synoptic_discussion(discussion)
            # Build keyword-based summary (find sentences with keywords)
            summary, counts = summarize_features(synoptic_text, all_keywords)
            # Get AI summary for comparison (optional - can use keyword summary as primary)
            ai_summary = get_ai_summary(discussion)
            processed_data[state][office] = {'discussion': discussion, 'url': url, 'synoptic_summary': summary, 'ai_summary': ai_summary}
            for k, v in counts.items():
                keyword_counts[k] += v
                keyword_map[k.lower()][state].append(office)

    # --- Build Content for the Right-Hand Pane ---
    print("Building HTML summary...")
    content_pane_html = f"""<h1 id="top">Shane's Super Top Secret Discussion Scraper</h1><p>Version: {script_version} | Executed: {execution_time_start}</p>"""
    content_pane_html += '<div class="state-links"><h3>Jump to State:</h3>'
    for state in sorted(processed_data.keys()):
        state_id = state_abbreviations.get(state, state).replace(' ', '_')
        content_pane_html += f'<a href("#{state_id}")">{state_abbreviations.get(state, state)}</a> '
    content_pane_html += "</div>"
    content_pane_html += '<h2>Overall Keyword Summary</h2><div class="keyword-summary">'
    if keyword_counts:
        for keyword in sorted(keyword_counts.keys()):
            count = keyword_counts[keyword]
            color = keyword_colors.get(keyword.lower(), '#E0E0E0')
            display_keyword = ' '.join(word.capitalize() for word in keyword.split())
            highlighted_summary_keyword = f'<span style="background-color:{color}; font-weight:bold; padding: 2px 0; border-radius: 3px;">{display_keyword}</span>'
            content_pane_html += f"<details><summary>{highlighted_summary_keyword} ({count} occurrences)</summary><ul>"
            for state in sorted(keyword_map[keyword].keys()):
                for office in sorted(keyword_map[keyword][state]):
                    content_pane_html += f'<li><a href("#{office.upper()}")">{state_abbreviations.get(state, state)} - {office.upper()}</a></li>'
            content_pane_html += "</ul></details>"
    else:
        content_pane_html += "<p>- No keywords found in any discussion.</p>"
    content_pane_html += "</div>"
    for state in sorted(processed_data.keys()):
        state_id = state_abbreviations.get(state, state).replace(' ', '_')
        content_pane_html += f"<h2 id='{state_id}'>--- {state.upper()} ---</h2>"
        for office in sorted(processed_data[state].keys()):
            data = processed_data[state][office]
            office_anchor_id = office.upper()
            content_pane_html += f"<hr><h3 id='{office_anchor_id}'>NWS Office: {office.upper()}</h3><h4>(keyword-Extracted Features):</h4>"
            if data['synoptic_summary']:
                # synoptic_summary is a list of sentences; join with <br> and highlight keywords
                summary_text = "<br>".join(data['synoptic_summary'])
                highlighted_summary = highlight_keywords(summary_text, keyword_colors)
                content_pane_html += f"<div style='background:#e8f5e9; padding:12px; border-radius:6px; margin-bottom:12px; white-space: normal;'>{highlighted_summary}</div>"
            else:
                content_pane_html += "<p>Office - Nothing Significant</p>"
            
            content_pane_html += "<h4>AI Summary (SynopticDiscussion):</h4>"
            if 'ai_summary' in data and data['ai_summary']:
                content_pane_html += f"<div style='background:#f0f7ff; padding:12px; border-radius:6px; margin-bottom:12px; white-space: normal;'>{data['ai_summary']}</div>"
            
            highlighted_discussion = highlight_keywords(data['discussion'], keyword_colors)
            content_pane_html += f"<details class='discussion-details'><summary>Full Discussion Text</summary><pre style='font-size: 1.6em;'>{highlighted_discussion}</pre></details>"
            content_pane_html += f"<p>Full Discussion Link: <a href='{data['url']}' target='_blank'>{data['url']}</a></p><p><a href='#top'>Back to Top</a></p>"

    # --- Assemble Final Dashboard ---
    final_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Shane's Super Top Secret Discussion Scraper</title>
        <style>
            body, html {
                margin: 0;
                padding: 20px;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            h1 {
                color: #333;
                margin-bottom: 20px;
            }
            h2 {
                color: #444;
                margin-top: 30px;
            }
            h3 {
                color: #555;
                margin: 15px 0;
            }
            pre {
                white-space: pre-wrap;
                word-wrap: break-word;
                background-color: #f8f8f8;
                padding: 10px;
                border-radius: 4px;
                border: 1px solid #ddd;
            }
            a {
                color: #0066cc;
            }
        </style>
    </head>
    <body>
        %s
    </body>
    </html>
    """ % content_pane_html

    # --- Save Output and Email ---
    # Save as .txt so NIPR email filters allow the attachment through
    output_filename = os.path.join(DATA_DIR, "Shane_Synoptic_Summary.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"Successfully saved to {output_filename}")
    
    # Deliver the email with the .txt attachment
    send_email_with_attachment(output_filename)


# --- JOB STATUS TRACKER ---
def update_job_status(job_name):
    status_file = "/home/progged-ish/projects/shanes-scraper/data/job_status.json"
    data = {}
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                data = json.load(f)
        except Exception:
            pass
            
    # Format the current UTC time as you wish (e.g. 05-Mar-2026 14:00Z)
    now_zulu = datetime.datetime.now(datetime.timezone.utc).strftime("%d-%b-%Y %H:%MZ")
    data[job_name] = now_zulu
    
    try:
        with open(status_file, "w") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Failed to update Job Status: {e}")


if __name__ == '__main__':
    try:
        main()
        update_job_status("Shanes Scraper")
    except Exception as e:
        import traceback
        print(f"CRITICAL ERROR: {e}")
        traceback.print_exc()
