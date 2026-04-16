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
    script_version = "6.0.0"
    execution_time_start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    print(f"Starting Shane's Super Top Secret Discussion Scraper v{script_version}")
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
    state_abbreviations = {'Canada': 'CAN', 'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ', 'Arkansas': 'AR', 'California': 'CA', ' Colorado': 'CO', 'Connecticut': 'CT', 'Delaware': 'DE', 'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI', 'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA', 'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME', 'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN', 'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE', 'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM', 'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH', 'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI', 'South Carolina': 'SC', 'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX', 'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA', 'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY'}
    
    # V5 HUD-style pill colors (dark mode friendly)
    keyword_colors = {
        'front': '#dc2626', 'fronts': '#dc2626', 
        'trough': '#f97316', 'troughs': '#f97316', 
        'shortwave': '#f59e0b',
        'dry line': '#eab308', 'dryline': '#eab308', 
        'ridge': '#84cc16', 
        'jet streak': '#06b6d4', 
        'surface low': '#3b82f6', 'upper low': '#3b82f6',
        'record high': '#ec4899', 'record low': '#3b82f6', 
        'record precipitation': '#10b981', 'record snowfall': '#94a3b8',
        'arctic': '#3b82f6'
    }
    
    # Keywords to search for (matching keywords in v4, but using the color map keys)
    all_keywords = list(keyword_colors.keys())
    
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

    # --- V5: Build Modern HUD HTML with Dark Mode & Pill Styling ---
    print("Building modern HUD HTML summary...")
    
    # Build state nav pills
    state_nav_pills = []
    for state in sorted(processed_data.keys()):
        state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
        active = "active" if state == sorted(processed_data.keys())[0] else ""
        state_nav_pills.append(f'<a class="nav-pill {active}" href="#{state_abbrev}">{state_abbrev}</a>')
    
    # Build keyword overview pills (sidebar stats)
    keyword_overview = []
    for keyword in sorted(keyword_counts.keys()):
        count = keyword_counts[keyword]
        pill_class = keyword.replace(' ', '-').split()[0] if ' ' in keyword else keyword
        if pill_class not in ['front', 'trough', 'dryline', 'ridge', 'shortwave', 'jetstreak', 'low', 'record']:
            pill_class = 'low'  # default to blue
        keyword_overview.append(f'<span class="stat-pill"><b>{keyword.capitalize()}</b>: {count}</span>')
    
    # Build keyword office links (sidebar section)
    keyword_office_links = []
    for keyword in sorted(keyword_counts.keys()):
        count = keyword_counts[keyword]
        # Build links for each office with this keyword
        office_links = []
        for state in sorted(keyword_map[keyword].keys()):
            for office in sorted(keyword_map[keyword][state]):
                state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
                office_links.append(f'<a class="keyword-link" href="#{state_abbrev}">{office.upper()}</a>')
        pill_class = keyword.replace(' ', '-').split()[0] if ' ' in keyword else keyword
        if pill_class not in ['front', 'trough', 'dryline', 'ridge', 'shortwave', 'jetstreak', 'low', 'record']:
            pill_class = 'low'
        keyword_office_links.append(f"""
<div class="keyword-item">
    <div class="keyword-label" style="color: var(--pill-{pill_class});">{keyword.capitalize()} ({count} occurrences)</div>
    <div class="keyword-link-list">{"".join(office_links)}</div>
</div>""")
    keyword_office_links_html = "".join(keyword_office_links)
    
    # Build state nav sidebar
    state_nav_sidebar = []
    for state in sorted(processed_data.keys()):
        state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
        state_nav_sidebar.append(f'<a class="nav-pill" href="#{state_abbrev}">{state_abbrev}</a>')
    
    # Process content pane - office cards with HUD styling
    content_pane_html = ""
    for state in sorted(processed_data.keys()):
        state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
        content_pane_html += f'<h2 id="{state_abbrev}">{state.upper()}</h2>'
        for office in sorted(processed_data[state].keys()):
            data = processed_data[state][office]
            office_anchor_id = office.upper()
            
            # Build keyword pills for this office
            keyword_pills = []
            if data['synoptic_summary']:
                for keyword in sorted(keyword_counts.keys()):
                    if keyword.lower() in ' '.join(data['synoptic_summary']).lower():
                        pill_class = keyword.replace(' ', '-').split()[0] if ' ' in keyword else keyword
                        if pill_class not in ['front', 'trough', 'dryline', 'ridge', 'shortwave', 'jetstreak', 'low', 'record']:
                            pill_class = 'low'
                        display_name = keyword.capitalize() if keyword != 'dry line' else 'Dryline'
                        keyword_pills.append(f'<span class="hud-pill {pill_class}">{display_name}</span>')
            
            # Format AI summary (replace bullets with paragraphs)
            ai_summary_formatted = data['ai_summary'].replace('-', '•').replace('\n', '<br>') if data['ai_summary'] else '[No AI summary available]'
            ai_summary_formatted = f'<div class="ai-summary"><span class="ai-label">AI SUMMARY</span>{ai_summary_formatted}</div>'
            
            # Keyword summary with pills
            keyword_summary_html = ""
            if data['synoptic_summary']:
                for line in data['synoptic_summary']:
                    # Extract keywords from this line and highlight
                    line_lower = line.lower()
                    highlighted_line = line
                    for keyword in sorted(keyword_counts.keys()):
                        if keyword in line_lower:
                            pill_class = keyword.replace(' ', '-').split()[0] if ' ' in keyword else keyword
                            if pill_class not in ['front', 'trough', 'dryline', 'ridge', 'shortwave', 'jetstreak', 'low', 'record']:
                                pill_class = 'low'
                            display_name = keyword.capitalize() if keyword != 'dry line' else 'Dryline'
                            highlighted_line = highlighted_line.replace(keyword, f'<span class="hud-pill {pill_class}">{display_name}</span>')
                    keyword_summary_html += f'<div class="keyword-line">{highlighted_line}</div>'
            
            content_pane_html += f"""
<div class="office-card">
    <div class="office-header">
        <span class="office-id">{office.upper()}</span>
        <span class="office-meta">{state.upper()} • {execution_time_start[:10]}</span>
        <a href="{data['url']}" target="_blank" class="office-link">View NWS</a>
    </div>
    <div class="hud-pills">{"".join(keyword_pills)}</div>
    <div class="ai-summary"><span class="ai-label">AI SUMMARY</span>{ai_summary_formatted}</div>
    <button class="details-toggle" type="button">
        <span>▼ KEYWORD FEATURES</span>
    </button>
    <div class="keyword-section">{keyword_summary_html}</div>
    <details>
        <summary class="details-toggle">Full Discussion</summary>
        <pre>{data['discussion']}</pre>
    </details>
    <div class="office-footer" style="margin-top:10px; padding:8px; background:var(--bg-primary); border-radius:6px; font-size:12px;">
        <a href="#top" style="color:var(--accent-cyan); text-decoration:none; float:right;">↑ Top</a>
        <span style="color:var(--text-muted);">Source: <a href="{data['url']}" style="word-break:break-all;">{data['url']}</a></span>
    </div>
</div>
"""

    # --- V6: Assemble Final HUD HTML with Dark Mode ---
    total_offices = sum(len(offices) for offices in processed_data.values())
    total_keywords = len(keyword_counts)
    
    # Load v6 template
    with open("/home/progged-ish/projects/shanes-scraper/html_templates/modern_dark_template_v6.html", "r") as f:
       template_content = f.read()
    
    # Replace placeholders
    final_html = template_content.replace("{EXEC_TIME}", execution_time_start)
    final_html = final_html.replace("{OFFICE_COUNT}", str(total_offices))
    final_html = final_html.replace("{KEYWORD_COUNT}", str(total_keywords))
    final_html = final_html.replace("{STATE_PILLS}", " ".join(state_nav_pills))
    final_html = final_html.replace("{STATE_PILLS_SIDEBAR}", " ".join(state_nav_sidebar))
    final_html = final_html.replace("{KEYWORD_STATS}", "".join(keyword_overview))
    final_html = final_html.replace("{KEYWORD_OFFICE_LINKS}", keyword_office_links_html)
    final_html = final_html.replace("{CONTENT_PANE}", content_pane_html)

    # --- Save Output and Email ---
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
