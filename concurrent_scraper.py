"""
Concurrent AI-Enhanced NWS Discussion Scraper v2.0
Scrapes Area Forecast Discussions (AFDs) from NWS offices with AI summaries.
"""

import asyncio
import aiohttp
from datetime import datetime
from typing import Tuple, Optional, Dict, Any
from bs4 import BeautifulSoup
import re
import os
import json

# Set up DATA_DIR
DATA_DIR = os.path.expanduser("~/projects/shanes-scraper/data")

# Set up summarizer - uses fast model (minimax-m2.5) for SYNOPTIC content extraction
from ai_summarizer.summarizer import HermesSummarizer, load_api_config, extract_synoptic_content, summarize_with_fast_model

ai_config = load_api_config()
summarizer = HermesSummarizer(**ai_config) if (ai_config.get('local_url') or ai_config.get('api_key')) else None

async def fetch_afd_async(wfo: str, session: aiohttp.ClientSession) -> Tuple[str, str, Optional[datetime]]:
    """Async fetch AFD discussion."""
    url = f"https://forecast.weather.gov/product.php?site={wfo.upper()}&issuedby={wfo.upper()}&product=AFD&format=txt&version=1&glossary=0"
    async with session.get(url, timeout=30) as response:
        text = await response.text()
        soup = BeautifulSoup(text, 'html.parser')
        pre = soup.find('pre')
        if pre:
            text = pre.get_text()
            zulu_match = re.search(r'^([A-Z]{4}\d{2})\s+K[A-Z]{3}\s+(\d{6})', text, re.MULTILINE)
            timestamp_obj = parse_zulu_timestamp(zulu_match.group(2)) if zulu_match else None
            return text, url, timestamp_obj
        raise Exception("No AFD text found")

def parse_zulu_timestamp(zulu_str: str) -> Optional[datetime]:
    """Parse Zulu timestamp string to datetime object."""
    try:
        return datetime.strptime(zulu_str, '%Y%m%d%H%M%S')
    except (ValueError, IndexError):
        return None

async def process_office(wfo: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
    """Fetch and process AFD for a single office with AI summarization."""
    try:
        afd_text, url, timestamp = await fetch_afd_async(wfo, session)
        
        ai_summary = ""
        if summarizer:
            try:
                ai_summary = summarizer.generate_summary(afd_text)
            except Exception as e:
                print(f"  AI Summary error for {wfo}: {type(e).__name__}")
        
        keywords = []
        keyword_patterns = [
            (r'thunderstorm', 'Thunderstorm'),
            (r'tornado', 'Tornado'),
            (r'flood', 'Flood'),
            (r'heavy rain', 'Heavy Rain'),
            (r'wind', 'Wind'),
            (r'ice', 'Ice'),
            (r'freezing', 'Freezing'),
            (r'snow', 'Snow'),
            (r'wind gust', 'Wind Gust'),
            (r'hail', 'Hail'),
        ]
        for pattern, keyword in keyword_patterns:
            if re.search(pattern, afd_text, re.IGNORECASE):
                keywords.append(keyword)
        
        return {
            'wfo': wfo,
            'text': afd_text,
            'url': url,
            'timestamp': timestamp,
            'ai_summary': ai_summary,
            'keywords': keywords
        }
    except Exception as e:
        print(f"  ✗ {wfo}: {type(e).__name__}: {str(e)[:100]}")
        return {
            'wfo': wfo,
            'text': '',
            'url': f"https://forecast.weather.gov/product.php?site={wfo.upper()}&issuedby={wfo.upper()}&product=AFD&format=txt",
            'timestamp': None,
            'ai_summary': '',
            'keywords': []
        }

async def main_concurrent(max_concurrent: int = 10) -> None:
    """Main entry point for concurrent scraping."""
    print("=" * 60)
    print("Shane's NWS Discussion Scraper v2.0 - AI Enhanced (Concurrent)")
    print("=" * 60)
    print(f"\n🤖 AI Summary Module: {'ENABLED' if summarizer else 'DISABLED'}")
    print(f"⏰ Execution time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    os.makedirs(DATA_DIR, exist_ok=True)
    
    all_offices = [
        'EKA', 'MTR', 'STO', 'HNX', 'LOX', 'SGX', 'PQR', 'PDT', 'MFR', 'SEW', 'OTX', 'ANC', 'FAI', 'JNU',
        'HFO', 'BOI', 'PIH', 'REV', 'VEF', 'LKN', 'SLC', 'FGZ', 'PSR', 'TWC', 'TFX', 'GGW', 'BYZ', 'MSO',
        'BOU', 'CYS', 'RIW', 'GJT', 'PUB', 'ABQ', 'BIS', 'FGF', 'ABR', 'FSD', 'LBF', 'GID', 'OAX', 'UNR',
        'GLD', 'ICT', 'DDC', 'TOP', 'OUN', 'TSA', 'AMA', 'FWD', 'HGX', 'MAF', 'SJT', 'BRO', 'EPZ', 'CRP',
        'DLH', 'MPX', 'DVN', 'DMX', 'ARX', 'EAX', 'LSX', 'SGF', 'LZK', 'SHV', 'LIX', 'GRB', 'MKX', 'ILX',
        'LOT', 'APX', 'DTX', 'MQT', 'IND', 'IWX', 'GRR', 'LMK', 'CLE', 'ILN', 'PBZ', 'JKL', 'PAH', 'OHX',
        'MRX', 'MEG', 'JAN', 'BMX', 'HUN', 'MOB', 'JAX', 'KEY', 'MFL', 'TAE', 'MLB', 'FFC', 'TBW', 'CHS',
        'GSP', 'CAE', 'ILM', 'RAH', 'MHX', 'AKQ', 'RNK', 'LWX', 'RLX', 'CTP', 'PHI', 'OKX', 'ALY', 'BGM',
        'BUF', 'BOX', 'BTV', 'GYX', 'CAR',
        'YVR', 'YYC', 'YWG', 'YYZ', 'YUL', 'YHZ'
    ]
    
    print(f"\n📡 Fetching {len(all_offices)} forecast discussions ({len([w for w in all_offices if w not in ['YVR','YYC','YWG','YYZ','YUL','YHZ']])} US offices)...")
    print("-" * 60)
    
    loop = asyncio.get_event_loop()
    connector = aiohttp.TCPConnector(limit=max_concurrent)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [process_office(wfo, session) for wfo in all_offices]
        results = await asyncio.gather(*tasks)
    
    us_offices = [r for r in results if r['wfo'] not in ['YVR', 'YYC', 'YWG', 'YYZ', 'YUL', 'YHZ']]
    
    processed_data = {'summaries': {}, 'keyword_counts': {}, 'keyword_summary': []}
    
    for result in us_offices:
        wfo = result['wfo']
        processed_data['summaries'][wfo] = {
            'text': result['text'],
            'ai_summary': result['ai_summary'],
            'url': result['url'],
            'timestamp': result['timestamp']
        }
        
        for keyword in result['keywords']:
            if keyword not in processed_data['keyword_counts']:
                processed_data['keyword_counts'][keyword] = 0
            processed_data['keyword_counts'][keyword] += 1
        
        if result['ai_summary']:
            processed_data['keyword_summary'].append({
                'wfo': wfo,
                'summary': result['ai_summary']
            })
        
        print(f"  ✓ {wfo}: {result['timestamp']}")
    
    start_time = datetime.utcnow()
    
    # Generate dashboard HTML (map generation skipped for now)
    output_html = generate_dashboard_html(
        processed_data,
        str(start_time),
        datetime.utcnow().isoformat() + " UTC",
        str(datetime.utcnow() - start_time),
        len(us_offices)
    )
    output_txt = output_html.replace('<', '&lt;').replace('>', '&gt;')
    
    html_path = os.path.join(DATA_DIR, 'shanes_nws_dashboard_v2.html')
    txt_path = os.path.join(DATA_DIR, 'shanes_nws_dashboard_v2.txt')
    
    with open(html_path, 'w', encoding='utf-8') as f:
        f.write(output_html)
    
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(output_txt)
    
    print(f"\n⏱️  Total execution time: {datetime.utcnow() - start_time}")
    print("\n============================================================")
    print(f"📊 Generating Dashboard...")
    print(f"✓ Dashboard saved to:")
    print(f"   HTML: {html_path}")
    print(f"   TXT:  {txt_path}")
    print(f"📁 HTML size: {os.path.getsize(html_path) / 1024:.1f} KB")
    print(f"📁 TXT size: {os.path.getsize(txt_path) / 1024:.1f} KB")
    print("\n============================================================")
    print(f"✓ Processing complete! {len(us_offices)} offices processed.")
    print("============================================================")

if __name__ == "__main__":
    start_time = datetime.utcnow()
    asyncio.run(main_concurrent())
