import os; os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
import requests
import concurrent.futures
import threading
import time
from bs4 import BeautifulSoup
import re
import base64
from collections import defaultdict
import datetime
import html
import os
import sys

def canonicalize_keyword(keyword):
    """Normalize keyword to its canonical form: singular, no spaces, lowercase."""
    kw = keyword.lower().strip()
    # Spaces removed: "dry line" -> "dryline"
    canonical_map = {
        'dry line': 'dryline',
        'dry lines': 'dryline',
        'drylines': 'dryline',
        'fronts': 'front',
        'troughs': 'trough',
        'ridges': 'ridge',
        'shortwaves': 'shortwave',
        'jet streaks': 'jet streak',
        'lows': 'low',
        'surface lows': 'surface low',
        'upper lows': 'upper low',
        'arctic air': 'arctic',
    }
    return canonical_map.get(kw, kw)


def keywords_to_pills(keywords_list):
    """
    Convert a list of keywords to HTML pills with proper CSS classes.
    Uses canonicalized forms for class names.
    """
    if not keywords_list:
        return ""
    
    pill_html = []
    seen = set()
    for kw in keywords_list:
        canonical = canonicalize_keyword(kw)
        if canonical in seen:
            continue
        seen.add(canonical)
        pill_class = canonical.replace(" ", "-")
        display_text = canonical.replace("-", " ").title()
        pill_html.append(f"<span class='hud-pill {pill_class}'>{display_text}</span>")
    return " ".join(pill_html)

import json
import smtplib
from email.message import EmailMessage

# --- Module-level constants ---
STATE_ABBREVS = {
    'Canada': 'CAN', 'Alabama': 'AL', 'Alaska': 'AK', 'Arizona': 'AZ',
    'Arkansas': 'AR', 'California': 'CA', 'Colorado': 'CO', 'Connecticut': 'CT',
    'Delaware': 'DE', 'Florida': 'FL', 'Georgia': 'GA', 'Hawaii': 'HI',
    'Idaho': 'ID', 'Illinois': 'IL', 'Indiana': 'IN', 'Iowa': 'IA',
    'Kansas': 'KS', 'Kentucky': 'KY', 'Louisiana': 'LA', 'Maine': 'ME',
    'Maryland': 'MD', 'Massachusetts': 'MA', 'Michigan': 'MI', 'Minnesota': 'MN',
    'Mississippi': 'MS', 'Missouri': 'MO', 'Montana': 'MT', 'Nebraska': 'NE',
    'Nevada': 'NV', 'New Hampshire': 'NH', 'New Jersey': 'NJ', 'New Mexico': 'NM',
    'New York': 'NY', 'North Carolina': 'NC', 'North Dakota': 'ND', 'Ohio': 'OH',
    'Oklahoma': 'OK', 'Oregon': 'OR', 'Pennsylvania': 'PA', 'Rhode Island': 'RI',
    'South Carolina': 'SC', 'South Dakota': 'SD', 'Tennessee': 'TN', 'Texas': 'TX',
    'Utah': 'UT', 'Vermont': 'VT', 'Virginia': 'VA', 'Washington': 'WA',
    'West Virginia': 'WV', 'Wisconsin': 'WI', 'Wyoming': 'WY', 'DC': 'DC',
    'Puerto Rico': 'PR',
}

# --- AI Model Configuration: Gemini Flash (primary) + LM Studio (fallback) ---
from openai import OpenAI
import socket

# Set timeout for API calls
socket.setdefaulttimeout(60)

# Primary: Google Gemini Flash via OpenAI-compatible endpoint
# gemini-2.5-flash is a thinking model — max_tokens covers thinking + output,
# so we set it higher (1024) so visible output isn't starved.
# Free tier: 5 RPM, 1500 RPD — rate limiter serializes calls to stay within quota.
GEMINI_API_KEY=os.env...EY", "")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MAX_TOKENS=***  # thinking model needs headroom

gemini_client = OpenAI(
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    api_key=GEMINI_API_KEY,
    timeout=60
) if GEMINI_API_KEY else None

class GeminiRateLimiter:
    """Thread-safe rate limiter for Gemini free tier (5 RPM).
    Spaces calls at least MIN_INTERVAL seconds apart.
    If a call can't be scheduled within MAX_WAIT seconds, returns False
    so the caller can fall through to LM Studio immediately."""
    MIN_INTERVAL = 12.2  # 5 RPM = 1 call per 12s, plus buffer
    MAX_WAIT = 5.0       # don't block a worker more than 5s

    def __init__(self):
        self._lock = threading.Lock()
        self._last_call = 0.0

    def acquire(self):
        """Returns True if rate slot acquired (caller should use Gemini),
        False if caller should fall through to LM Studio immediately."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_call
            wait_needed = max(0, self.MIN_INTERVAL - elapsed)
            if wait_needed > self.MAX_WAIT:
                return False
            if wait_needed > 0:
                time.sleep(wait_needed)
            self._last_call = time.monotonic()
            return True

_gemini_limiter = GeminiRateLimiter()

# Fallback: Local LM Studio instance (4070 Ti 12GB) running qwen2.5-7b-instruct
lm_client = OpenAI(
    base_url="http://10.0.0.94:1234/v1",
    api_key="lm-studio",
    timeout=60
)
LM_STUDIO_MODEL = "qwen2.5-7b-instruct"

# Active model indicator
FAST_MODEL = GEMINI_MODEL if GEMINI_API_KEY else LM_STUDIO_MODEL
_active_backend = "gemini" if GEMINI_API_KEY else "lm-studio"

def call_fast_model(messages, model=None, temperature=0.3, max_tokens=256):
    """
    Call LM Studio for fast office-level summarization.
    Used for the 137 per-office calls that run in parallel.
    Strips thinking blocks from reasoning models.
    """
    try:
        response = lm_client.chat.completions.create(
            model=LM_STUDIO_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=False
        )
        results = []
        for choice in response.choices:
            content = choice.message.content or ""
            content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()
            results.append({"message": {"content": content}})
        return {"choices": results}
    except Exception as e:
        print(f"  [LM Studio error] {type(e).__name__}: {e}")
        raise


def call_gemini(messages, temperature=0.3, max_tokens=1024):
    """
    Call Gemini Flash for high-value synthesis calls (regional rollup, CONUS bulletin).
    Rate-limited to respect free tier (5 RPM, 20 RPD). Runs sequentially.
    Falls back to LM Studio if Gemini is unavailable or quota exhausted.
    Strips thinking blocks from Gemini's reasoning output.
    """
    if gemini_client is None:
        print("  [Gemini] No API key, using LM Studio")
        return call_fast_model(messages, temperature=temperature, max_tokens=max_tokens)

    if not _gemini_limiter.acquire():
        print("  [Gemini] Rate slot unavailable, using LM Studio")
        return call_fast_model(messages, temperature=temperature, max_tokens=max_tokens)

    try:
        gemini_max = max(max_tokens, GEMINI_MAX_TOKENS)
        response = gemini_client.chat.completions.create(
            model=GEMINI_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=gemini_max,
            stream=False
        )
        results = []
        for choice in response.choices:
            content = choice.message.content or ""
            content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()
            results.append({"message": {"content": content}})
        return {"choices": results}
    except Exception as e:
        print(f"  [Gemini fallback] {type(e).__name__}: {e} — routing to LM Studio")
        return call_fast_model(messages, temperature=temperature, max_tokens=max_tokens)

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
        msg['Subject'] = "Shane's Scraper - NWS Synoptic Analysis"
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

def load_nws_stations_csv(csv_path="/home/progged-ish/projects/shanes-scraper/NWS_Stations.csv"):
    """Load NWS stations CSV and return dict mapping station ID to region, and station ID to office name."""
    import csv
    station_region_map = {}
    station_name_map = {}
    try:
        with open(csv_path, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                station_id = row.get('Station ID', '').strip().upper()
                if not station_id:
                    station_id = row.get('Station', '').strip().upper()
                region = row.get('Region', '').strip()
                office_name = row.get('Office Name', '').strip()
                if station_id and region:
                    station_region_map[station_id] = region
                if station_id and office_name:
                    station_name_map[station_id] = office_name
    except Exception as e:
        print(f"Warning: Could not load NWS stations CSV: {e}")
    return station_region_map, station_name_map


def process_office(args):
    """Process a single office - this runs in parallel."""
    state, office, idx, all_keywords = args
    office_id = office.upper()
    
    print(f"[{idx+1}] Fetching {office_id}...")
    
    discussion, url = get_forecast_discussion(office_id)
    synoptic_text = extract_synoptic_discussion(discussion)
    
    # Build keyword-based summary
    summary, counts = summarize_features(synoptic_text, all_keywords)
    
    # Get AI summary for this office using fast model (parallel-ready)
    ai_summary, ai_time = get_fast_model_summary(discussion, office_id)
    
    return {
        'state': state,
        'office': office,
        'discussion': discussion,
        'url': url,
        'synoptic_summary': summary,
        'ai_summary': ai_summary,
        'counts': counts,
        'ai_time': ai_time  # Track per-office fast model timing
    }


def synthesize_conus_outlook(processed_data, keyword_counts):
    """Generate CONUS summary using regional rollup: synthesize by region first, then roll up into a national bulletin.
    
    Two-pass architecture:
    Pass 1: Summarize office summaries by NWS region (4 calls, each ~10-20 offices)
    Pass 2: Synthesize the 4 regional summaries into one national bulletin
    
    This avoids blowing the model context by feeding all 147+ offices at once.
    """
    from collections import defaultdict
    station_region_map, station_name_map = load_nws_stations_csv()
    
    # Group office AI summaries by NWS region
    region_summaries = defaultdict(list)
    for state, offices in processed_data.items():
        if state.startswith('_'):
            continue
        for office, data in offices.items():
            if 'ai_summary' in data and data['ai_summary'] and not data['ai_summary'].startswith('['):
                region = station_region_map.get(office.upper(), 'Unknown')
                region_summaries[region].append(data['ai_summary'])
    
    if not region_summaries:
        # Fallback to keyword counts
        conus_summary = f"# CONUS Synoptic Summary\n\n"
        conus_summary += f"## Overall Patterns\n\n"
        for kw, cnt in sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            conus_summary += f"- {kw.capitalize()}: {cnt} occurrences\n"
        conus_summary += f"\n## Regional Breakdown\n\n"
        return conus_summary, {}
    
    # --- PASS 1: Regional synthesis ---
    # Synthesize each region's office summaries into a regional narrative
    REGIONAL_SYSTEM_PROMPT = """You are a Duty Synoptician writing a regional weather brief for the forecast desk.

You will receive multiple office-level synoptic summaries from a single NWS region. Each office covers part of a larger weather pattern.

MERGE AND DE-DUPLICATE: Recognize that adjacent offices are describing the SAME weather features from different vantage points. Merge overlapping reports into unified descriptions of regional-scale systems.

OUTPUT: 2-3 sentences describing the dominant synoptic pattern across this region. Active voice. No bullets, no lists, no markdown, no filler. Start directly with the pattern.

AVOID TEMPLATE PHRASING: Do not repeat boilerplate like "undercuts the retreating ridge" or "steepening lapse rates and enhancing deep-layer shear." Each region has distinct dynamics — describe them specifically."""

    regional_narratives = {}
    for region_name, summaries in sorted(region_summaries.items()):
        concatenated = "\n\n".join(summaries)
        # Truncate to fit context — each region should have 10-20 offices, ~8000 chars max
        if len(concatenated) > 12000:
            concatenated = concatenated[:12000] + "\n\n[...truncated...]"
        
        try:
            response = call_fast_model(
                messages=[
                    {"role": "system", "content": REGIONAL_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Office-level synoptic summaries from the {region_name}:\n\n{concatenated}"}
                ],
                temperature=0.4,
                max_tokens=256
            )
            if "choices" in response and len(response["choices"]) > 0:
                regional_narratives[region_name] = response["choices"][0]["message"].get("content", "").strip()
            else:
                regional_narratives[region_name] = ""
        except Exception as e:
            print(f"  [REGION ERROR] {region_name}: {type(e).__name__}: {e}")
            regional_narratives[region_name] = ""
    
    # --- PASS 2: National synthesis from regional narratives ---
    # Now feed only the 4 regional narratives (much smaller context) to produce the CONUS bulletin
    valid_regions = {k: v for k, v in regional_narratives.items() if v}
    
    if valid_regions:
        regional_context = "\n\n".join(f"## {region}\n{narrative}" for region, narrative in valid_regions.items())
        
        CONUS_SYSTEM_PROMPT = """You are the Lead National Synoptician preparing the continental CONUS weather bulletin.

You will receive 4 regional synoptic narratives (Western, Central, Southern, Eastern). Each is already filtered to pure synoptic mechanics.

SYNTHESIZE: Merge overlapping features across regions into continental-scale systems. A front described by both Southern and Eastern regions is ONE front. A trough spanning Central and Western regions is ONE trough.

STRUCTURE: 2-3 paragraphs. Open with the dominant longwave pattern and its evolution, then detail the key shortwave/surface reflections and their interactions, close with what's coming next.

TONE: Professional internal forecast desk brief. Discuss advection, cyclogenesis, jet dynamics. No public-facing language.

NO: bullets, lists, markdown, introductory phrases, or concluding phrases. Output ONLY the bulletin text.

AVOID TEMPLATE PHRASING: Do not reuse formulaic phrases like "undercuts the retreating ridge" or "steepening lapse rates and enhancing deep-layer shear." Write each paragraph with fresh, specific language about the actual pattern."""

        try:
            print("Generating CONUS bulletin from regional rollups...")
            response = call_fast_model(
                messages=[
                    {"role": "system", "content": CONUS_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Regional narratives to synthesize:\n\n{regional_context}"}
                ],
                temperature=0.4,
                max_tokens=1024
            )
            if "choices" in response and len(response["choices"]) > 0:
                expert_summary = response["choices"][0]["message"].get("content", "").strip()
            else:
                expert_summary = ""
        except Exception as e:
            print(f"Error generating CONUS bulletin: {e}")
            expert_summary = ""
    else:
        expert_summary = ""
    
    # Fallback if CONUS synthesis produced nothing
    if not expert_summary:
        expert_summary = "CONUS synthesis unavailable — regional data below.\n\n"
        for region, narrative in valid_regions.items():
            expert_summary += f"**{region}**: {narrative}\n\n"
    
    # Build final CONUS output with HTML wrapping
    conus_summary = f"<details open><summary>Click to expand CONUS Expert Summary</summary>\n\n{expert_summary}\n\n</details>\n\n"
    conus_summary += f"## Regional Overview\n\n"
    
    # Regional breakdown with keyword pills
    region_offices = defaultdict(list)
    for state, offices in processed_data.items():
        if state.startswith('_'):
            continue
        for office in offices:
            region = station_region_map.get(office.upper(), 'Unknown')
            region_offices[region].append(office)
    
    for region in sorted(region_offices.keys()):
        offices = region_offices[region]
        region_keyword_counts = {}
        for office in offices:
            for state, office_data in processed_data.items():
                if state.startswith('_'):
                    continue
                if office in office_data:
                    counts = office_data[office].get('counts', {})
                    for kw, cnt in counts.items():
                        region_keyword_counts[kw] = region_keyword_counts.get(kw, 0) + cnt
        region_keywords = sorted(region_keyword_counts.items(), key=lambda x: x[1], reverse=True)[:5]
        keywords_list = [kw for kw, cnt in region_keywords]
        
        regional_output = f"### {region}\n\n"
        regional_output += f"Offices: {', '.join(sorted(offices))}\n\n"
        if keywords_list:
