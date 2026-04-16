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
import json
import smtplib
from email.message import EmailMessage

def canonicalize_keyword(keyword):
    """Normalize keyword to its canonical form: singular, no spaces, lowercase."""
    kw = keyword.lower().strip()
    canonical_map = {
        'dry line': 'dryline',
        'dry lines': 'dryline',
        'dry lines': 'dryline',
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

# --- AI Model Configuration: Gemini Flash (regional/CONUS) + LM Studio (per-office) ---
from openai import OpenAI
import socket

# Set timeout for API calls
socket.setdefaulttimeout(60)

# Primary synthesis: Google Gemini Flash via OpenAI-compatible endpoint
# gemini-2.5-flash is a thinking model — max_tokens covers thinking + output,
# so we set it higher (1024) so visible output isn't starved.
# Free tier: 5 RPM, 1500 RPD — rate limiter serializes calls to stay within quota.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
GEMINI_MAX_TOKENS = 1024  # thinking model needs headroom

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

# Per-office: Local LM Studio instance (4070 Ti 12GB) running qwen2.5-7b-instruct
lm_client = OpenAI(
    base_url="http://10.0.0.94:1234/v1",
    api_key="lm-studio",
    timeout=60
)
LM_STUDIO_MODEL = "qwen2.5-7b-instruct"

# Active model indicator — offices ALWAYS use LM Studio, Gemini is for synthesis only
FAST_MODEL = LM_STUDIO_MODEL
_active_backend = "gemini+lm-studio" if GEMINI_API_KEY else "lm-studio-only"

def call_fast_model(messages, model=None, temperature=0.3, max_tokens=256):
    """
    Call LM Studio qwen2.5-7b-instruct for fast office-level summarization.
    Used for the 137 per-office calls that run in parallel.
    Strips thinking blocks from reasoning models (safety net).
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
            # Strip thinking blocks (safety net for reasoning models)
            content = re.sub(r'<think>.*?</think>\s*', '', content, flags=re.DOTALL).strip()
            results.append({"message": {"content": content}})
        return {"choices": results}
    except Exception as e:
        print(f"  [LM Studio error] {type(e).__name__}: {e}")
        raise


def call_gemini(messages, temperature=0.3, max_tokens=1024):
    """
    Call Gemini Flash for high-value synthesis calls (4 regional rollups + 1 CONUS bulletin).
    Rate-limited to respect free tier (5 RPM, ~1500 RPD). Runs sequentially.
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
            # Strip thinking blocks from Gemini
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
    
    Two-pass architecture (HYBRID v8.2):
    Pass 1: Summarize office summaries by NWS region (4 calls to Gemini via call_gemini)
    Pass 2: Synthesize the 4 regional summaries into one national bulletin (1 call to Gemini via call_gemini)
    
    This avoids blowing the model context by feeding all 147+ offices at once.
    Gemini handles the high-value synthesis; offices use LM Studio via call_fast_model.
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
    
    # --- PASS 1: Regional synthesis via Gemini ---
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
            # v8.2: Regional synthesis goes to Gemini (high quality), falls back to LM Studio
            response = call_gemini(
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
    
    # --- PASS 2: National synthesis from regional narratives via Gemini ---
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
            print("Generating CONUS bulletin from regional rollups via Gemini...")
            # v8.2: CONUS synthesis goes to Gemini (high quality), falls back to LM Studio
            response = call_gemini(
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
            regional_output += f"Key features: {keywords_to_pills(keywords_list)}\n\n"
        if region in regional_narratives and regional_narratives[region]:
            regional_output += f"{regional_narratives[region]}\n\n"
        conus_summary += regional_output
    
    return conus_summary, regional_narratives


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

# --- V8: Parallel AI Call Helpers ---
def get_fast_model_summary(text: str, office_id: str = None, fast_model_name: str = "qwen2.5-7b-instruct") -> tuple[str, float]:
    """
    V9.1: Synoptic feature extraction using split system/user prompt architecture.
    Feeds the FULL AFD text (not extracted sections) to capture synoptic info
    scattered across all AFD sections. Rules in the user message (right before
    AFD text) suppress impact/product leakage better than system-only.
    Returns (summary_string, elapsed_seconds) tuple.
    """
    import time as _time
    start_time = _time.time()
    
    # V9: Feed the FULL discussion text, not extracted synoptic section
    afd_text = text
    
    if not afd_text:
        return ("[No content to summarize]", 0.0)
    
    # Truncate long AFD texts to fit local model context (16K chars)
    if len(afd_text) > 16000:
        afd_text = afd_text[:16000]
    
    SYSTEM_PROMPT = """You are a synoptic analyst scanning NWS Area Forecast Discussions for operational weather intelligence.

Extract ONLY synoptic-scale features the forecaster identifies. Report:
- Positioning and evolution of troughs, ridges, fronts, drylines, surface lows, shortwaves, and jet streaks
- Interactions between features (e.g., shortwave ejecting out of base of longwave trough)
- Mesoscale features tied to synoptic forcing: dryline position and mixing evolution, outflow boundaries, low-level jets, convective initiation timing relative to synoptic lift, model uncertainty on these features
- Anything the forecaster notes that models may struggle with (e.g., dryline position, phasing, amplification doubts)

Format: 2-4 short statements. Each statement names the feature first, then its position or behavior. No bullets, no markdown."""

    USER_PREFIX = """Extract synoptic features from this AFD. STRICT RULES:
- If the AFD mentions a Watch, Warning, Advisory, or Red Flag — do NOT repeat it. Name the synoptic driver instead.
- No impact language ("severe storms possible", "hard freeze likely", "critical fire weather"). Only the feature causing it.
- No precipitation totals, snow totals, RH values, or fire weather indices.
- No public-facing phrasing.

If the AFD says "Red Flag Warning due to low RH and gusty winds" you write: "Dry southwesterly flow with low mixing heights."

EXAMPLE of good output (format only, do not copy or paraphrase this content):
Longwave trough anchored over the eastern Pacific with shortwaves rotating through the base. Amplifying ridge over the Intermountain West nudging the trough axis eastward by midweek. Model spread on timing of the next shortwave ejection.

AFD TEXT:
"""
    
    try:
        response_data = call_fast_model(
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PREFIX + afd_text}
            ],
            temperature=0.3,
            model=fast_model_name
        )

        if "choices" in response_data and len(response_data["choices"]) > 0:
            message = response_data["choices"][0]["message"]
            if "content" in message:
                elapsed = _time.time() - start_time
                return (message["content"].strip(), elapsed)
    except Exception as e:
        # Fallback to minimal summary if AI fails - but track the error
        return (generate_minimal_summary(afd_text), 0.0)
    
    return ("[AI call failed]", 0.0)


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
    script_version = "8.2.0"
    execution_time_start = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    
    # Start wall-clock timing
    wall_start_time = datetime.datetime.now()
    
    print(f"Starting Shane's Synoptic Scraper v{script_version}")
    print(f"Backend: {_active_backend}")
    print(f"  Per-office: qwen2.5-7b-instruct via LM Studio (parallel, 8 workers)")
    if GEMINI_API_KEY:
        print(f"  Synthesis: gemini-2.5-flash via Gemini API (regional + CONUS, rate-limited)")
    else:
        print(f"  Synthesis: qwen2.5-7b-instruct via LM Studio (Gemini key not set)")
    print(f"Execution started at: {execution_time_start}")
    
    # --- DATA DICTIONARIES ---
    # V9: AK/CAN removed (per user preference — use HRRR for AK high-res, CAN not CONUS)
    all_offices_synoptic = {
        'California': ['EKA', 'MTR', 'STO', 'HNX', 'LOX', 'SGX'], 'Oregon': ['PQR', 'PDT', 'MFR'], 'Washington': ['SEW', 'OTX'], 'Hawaii': ['HFO'], 'Idaho': ['BOI', 'PIH'], 'Nevada': ['REV', 'LKN', 'VEF'], 'Utah': ['SLC'],
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
    state_abbreviations = STATE_ABBREVS
    
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

    # --- Parallel Processing Loop with ThreadPoolExecutor ---
    office_list = []
    idx = 0
    for state, offices in all_offices_synoptic.items():
        for office in offices:
            office_list.append((state, office, idx))
            idx += 1

    print(f"Processing {len(office_list)} offices in parallel...")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        futures = [executor.submit(process_office, (state, office, idx, all_keywords)) for state, office, idx in office_list]
        
        # Track parallel AI timing
        total_ai_time = 0.0
        concurrent_offices_count = 0
        
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            state, office = result['state'], result['office']
            processed_data[state][office] = {
                'discussion': result['discussion'],
                'url': result['url'],
                'synoptic_summary': result['synoptic_summary'],
                'ai_summary': result['ai_summary'],
                'counts': result['counts'],
                'ai_elapsed': result.get('ai_time', 0.0),
            }
            if 'ai_time' in result and result['ai_time'] > 0:
                total_ai_time += result['ai_time']
                concurrent_offices_count += 1
            
            for k, v in result['counts'].items():
                keyword_counts[k] += v
                keyword_map[k.lower()][state].append(office)
    
    # Print parallel AI timing breakdown
    print(f"Parallel AI timing: {total_ai_time:.1f}s total for {concurrent_offices_count} offices with valid AI call timing")
    if concurrent_offices_count > 0:
        print(f"  Average per office: {total_ai_time/concurrent_offices_count:.2f}s")

    # --- Generate CONUS Summary with Regional Breakdown ---
    print("Generating CONUS summary with regional breakdown via Gemini...")
    conus_summary, conus_regions = synthesize_conus_outlook(processed_data, keyword_counts)
    
    # Store CONUS summary for HTML injection
    processed_data['_conus_summary'] = conus_summary
    processed_data['_conus_regions'] = conus_regions

    # --- Build Modern HUD HTML with Dark Mode & Pill Styling ---
    print("Building modern HUD HTML summary...")
    
    # Build state nav pills
    state_nav_pills = []
    for state in sorted(processed_data.keys()):
        if state.startswith('_'):
            continue
        state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
        state_nav_pills.append(f'<a class="nav-pill" href="#{state_abbrev}">{state_abbrev}</a>')
    
    # Build keyword office links (sidebar - Keyword Office Links section)
    keyword_office_links_html = ""
    for keyword in sorted(keyword_counts.keys()):
        # Get the link list for this keyword across all states
        keyword_links = []
        for state in sorted(keyword_map[keyword.lower()].keys()):
            offices = keyword_map[keyword.lower()][state]
            for office in offices:
                office_upper = office.upper()
                state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
                kw_class = canonicalize_keyword(keyword).replace(" ", "-")
                link = f'<a href="#{state_abbrev}" class="keyword-link kw-link-{kw_class}" title="{state}">{office_upper}</a>'
                if link not in keyword_links:
                    keyword_links.append(link)
        if keyword_links:
            kw_class = canonicalize_keyword(keyword).replace(" ", "-")
            keyword_office_links_html += f'<div class="keyword-item kw-section-{kw_class}"><span class="keyword-label kw-label-{kw_class}">{keyword.capitalize()}</span><div class="keyword-link-list">{"".join(keyword_links)}</div></div>'

    # Process content pane - office cards with HUD styling
    content_pane_html = ""
    for state in sorted(processed_data.keys()):
        # Skip metadata keys
        if state.startswith('_'):
            continue
        state_abbrev = state_abbreviations.get(state, state).replace(' ', '_')
        content_pane_html += f'<h2 id="{state_abbrev}">{state.upper()}</h2>'
        for office in sorted(processed_data[state].keys()):
            data = processed_data[state][office]
            office_anchor_id = office.upper()
            
            # Build keyword pills for this office using keywords_to_pills
            keyword_pills = []
            if data['synoptic_summary']:
                found_kws = []
                for keyword in sorted(keyword_counts.keys()):
                    if keyword in ' '.join(data['synoptic_summary']).lower():
                        found_kws.append(keyword)
                keyword_pills_html = keywords_to_pills(found_kws)
            else:
                keyword_pills_html = ""
            
            # Format AI summary (replace bullets with paragraphs)
            ai_summary_formatted = data['ai_summary'].replace('-', '•').replace('\n', '<br>') if data['ai_summary'] else '[No AI summary available]'
            
            # Keyword summary with pills
            keyword_summary_html = ""
            if data['synoptic_summary']:
                for line in data['synoptic_summary']:
                    # Extract keywords from this line and highlight
                    line_lower = line.lower()
                    highlighted_line = line
                    for keyword in sorted(keyword_counts.keys()):
                        if keyword in line_lower:
                            display_name = keyword.capitalize() if keyword != 'dry line' else 'Dryline'
                            highlighted_line = highlighted_line.replace(keyword, f'<span class="hud-pill {canonicalize_keyword(keyword).replace(" ", "-")}">{display_name}</span>')
                    keyword_summary_html += f'<div class="keyword-line">{highlighted_line}</div>'
            
            content_pane_html += f"""
<div class="office-card" id="{office_anchor_id}">
    <div class="office-header">
        <span class="office-id">{office.upper()}</span>
        <span class="office-meta">{state.upper()} • {execution_time_start[:10]}</span>
        <a href="{data['url']}" target="_blank" class="office-link">View NWS</a>
    </div>
    <div class="hud-pills">{keyword_pills_html}</div>
    <div class="ai-summary"><span class="ai-label">AI SUMMARY</span>{ai_summary_formatted}</div>
    <button class="collapsible-header" type="button" onclick="toggleSection('kw-{office_anchor_id}')">
        KEYWORD FEATURES <span class="toggle-arrow">▶</span>
    </button>
    <div class="collapsible-body" id="kw-{office_anchor_id}">{keyword_summary_html}</div>
    <button class="collapsible-header" type="button" onclick="toggleSection('disc-{office_anchor_id}')">
        FULL DISCUSSION <span class="toggle-arrow">▶</span>
    </button>
    <div class="collapsible-body" id="disc-{office_anchor_id}"><pre>{data['discussion']}</pre></div>
    <div class="office-footer">
        <a href="#top" style="color:var(--accent); text-decoration:none; float:right;">↑ Top</a>
        <span style="color:var(--text-dim);">Source: <a href="{data['url']}" style="word-break:break-all;">{data['url']}</a></span>
    </div>
</div>
"""

    # --- Assemble Final HUD HTML with v8 Template ---
    
    # Insert CONUS summary at top of content pane
    conus_summary_html = ""
    if '_conus_summary' in processed_data:
        conus_summary = processed_data['_conus_summary']
        # Convert markdown headers to HTML headings
        converted_summary = re.sub(r'^### (.+)$', r'<h4 style="color:var(--accent); margin-top:16px; margin-bottom:8px;">\1</h4>', conus_summary, flags=re.MULTILINE)
        converted_summary = re.sub(r'^## (.+)$', r'<h3 style="color:var(--accent); margin-top:20px; margin-bottom:12px;">\1</h3>', converted_summary, flags=re.MULTILINE)
        converted_summary = re.sub(r'^# (.+)$', r'<h2 style="color:var(--accent); margin-top:24px; margin-bottom:16px;">\1</h2>', converted_summary, flags=re.MULTILINE)
        # Convert double newlines to paragraph breaks
        converted_summary = re.sub(r'\n\n+', r'</p><p style="margin-bottom:12px;">', converted_summary)
        # Convert single newlines to <br>
        converted_summary = converted_summary.replace('\n', '<br>')
        if not converted_summary.startswith('<p'):
            converted_summary = f'<p style="margin-bottom:12px;">{converted_summary}</p>'
        converted_summary = converted_summary.replace('**', '<strong>').replace('`', '<code>')
        conus_summary_html = f'<div class="conus-summary" style="margin-bottom:32px; padding:20px; background:var(--bg-panel); border-left:4px solid var(--accent); border-radius:8px;"><h3 style="color:var(--accent); margin-bottom:12px;">CONUS SYNOPSIS</h3><div style="font-size:14px; line-height:1.6;">{converted_summary}</div></div>'
    
    # Load v9 template
    with open("/home/progged-ish/projects/shanes-scraper/html_templates/modern_dark_template_v9.html", "r") as f:
       template_content = f.read()
    
    # Replace placeholders
    final_html = template_content.replace("{EXEC_TIME}", execution_time_start)
    final_html = final_html.replace("{STATE_PILLS}", " ".join(state_nav_pills))
    final_html = final_html.replace("{KEYWORD_OFFICE_LINKS}", keyword_office_links_html)
    final_html = final_html.replace("{CONTENT_PANE}", conus_summary_html + content_pane_html)

    # --- Save Output and Email ---
    output_filename = os.path.join(DATA_DIR, "Shane_Synoptic_Summary.txt")
    with open(output_filename, "w", encoding="utf-8") as f:
        f.write(final_html)
    
    print(f"Successfully saved to {output_filename}")
    
    # Deliver the email with the .txt attachment
    send_email_with_attachment(output_filename)
    
    # Export AFD data as JSON for dashboard
    export_afd_json(processed_data, keyword_counts, execution_time_start)
    
    # Print wall-clock timing
    wall_end_time = datetime.datetime.now()
    wall_duration = (wall_end_time - wall_start_time).total_seconds()
    print(f"Wall-clock duration: {wall_duration:.1f} seconds")


def export_afd_json(processed_data, keyword_counts, execution_time):
    """Export processed AFD data as JSON for the Flask dashboard and external consumers.
    
    V9: Includes raw AFD text, AI elapsed time, and synoptic summary for each office.
    """
    export_data = {
        "execution_time": execution_time,
        "keyword_counts": dict(keyword_counts),
        "offices": {}
    }
    for state, offices in processed_data.items():
        if state.startswith('_'):
            continue
        for office, data in offices.items():
            export_data["offices"][office] = {
                "state": state,
                "ai_summary": data.get('ai_summary', ''),
                "synoptic_summary": data.get('synoptic_summary', []),
                "url": data.get('url', ''),
                "keyword_counts": dict(data.get('counts', {})),
                "ai_elapsed_seconds": data.get('ai_elapsed', 0.0),
                "raw_afd": data.get('discussion', ''),
            }
    # Include CONUS summary if available
    if '_conus_summary' in processed_data:
        export_data["conus_summary"] = processed_data['_conus_summary']
    # Include regional narratives if available
    if '_conus_regions' in processed_data:
        export_data["regional_narratives"] = processed_data['_conus_regions']
    try:
        with open(os.path.join(DATA_DIR, "afd_latest.json"), "w") as f:
            json.dump(export_data, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not export AFD JSON: {e}")


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
