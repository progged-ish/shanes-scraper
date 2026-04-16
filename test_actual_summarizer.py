#!/usr/bin/env python3
"""
Test script to use the actual HermesSummarizer class
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Try to import from the ai_summarizer module
try:
    from ai_summarizer.summarizer import HermesSummarizer, extract_synoptic_content
    
    def test_actual_summarizer():
        """Test using the actual HermesSummarizer class"""
        print("Testing extract_synoptic_content function...")
        
        # Test with a realistic AFD snippet
        test_text = """AREA FORECAST DISCUSSION
FXUS66 KBOU 040724

SYNOPSIS...
A strong high pressure system will dominate the region through the week with dry conditions. A cold front will approach from the northwest later in the week bringing potential for showers and thunderstorms.

TEMPERATURES...
Highs in the 70s today, falling to the 60s by Wednesday.
"""
        
        synoptic = extract_synoptic_content(test_text)
        print(f"Extracted {len(synoptic)} chars of SYNOPSIS content")
        print(f"Content: {synoptic[:200]}...")
        
        print("\nInitializing HermesSummarizer...")
        summarizer = HermesSummarizer()
        
        print("\nGenerating summary...")
        try:
            summary = summarizer.generate_summary(test_text, debug=True)
            print(f"SUCCESS: Generated summary")
            print(f"Summary: {summary}")
        except Exception as e:
            print(f"ERROR generating summary: {e}")
            import traceback
            traceback.print_exc()
    
    if __name__ == "__main__":
        test_actual_summarizer()

except ImportError as e:
    print(f"Import error: {e}")
    print("Make sure ai_summarizer module is available")
