#!/usr/bin/env python3
"""Quick test to verify NAM downloads functionality."""

import sys
sys.path.insert(0, '.')

from shanes_nws_scraper_v2_fixed import extract_nam_mentions

# Test the NAM extraction function
test_text = """
The 12z NAM shows increasing instability across the region.
Recent NAM runs indicate better moisture return.
The NAM forecast suggests higher temperatures.
"""

mentions = extract_nam_mentions(test_text)
print(f"Found {len(mentions)} NAM mentions:")
for mention in mentions:
    print(f"  - {mention['mention']}: {mention['context'][:50]}...")
