#!/usr/bin/env python3
"""
Test script with mock NWS data for shanes-scraper.
Use this when the NWS API is blocked or for testing.
"""

from shanes_nws_scraper_v2_fixed import (
    generate_keyword_summary, generate_office_summaries, 
    get_state_abbrev, get_ai_summary, generate_dashboard_html,
    KEYWORD_COLORS
)

# Mock NWS discussion data
MOCK_DATA = """
FORECAST DISCUSSION
National Weather Service
Anchorage AK
1130 PM AKDT Wed Mar 31 2026

...dryline activity continues across the plains today with several 
severe weather outbreaks. Fronts are moving through the region...

...record high temperatures expected in the southwest this weekend...

...ice and snow conditions remain hazardous for travel. Thunderstorm 
activity is expected to continue through the evening hours. Shortwave
disturbances are moving through the area...

...surface low pressure developing in the northern plains. Troughs
of low pressure will bring clouds and precipitation...
"""

def create_mock_processed_data():
    """Create mock processed data for testing."""
    import json
    from collections import defaultdict
    
    # Mock keyword occurrences
    keyword_occurrences = defaultdict(list)
    keyword_occurrences['dryline'].append({
        'office': 'ANC',
        'state': 'AK',
        'text': 'dryline activity continues across the plains today'
    })
    keyword_occurrences['dryline'].append({
        'office': 'BOU',
        'state': 'CO',
        'text': 'dryline conditions expected in the mountains'
    })
    
    keyword_occurrences['severe'].append({
        'office': 'DMX',
        'state': 'TX',
        'text': 'severe weather outbreak expected in central texas'
    })
    
    keyword_occurrences['front'].append({
        'office': 'ABQ',
        'state': 'NM',
        'text': 'fronts moving through the region bringing rain'
    })
    
    keyword_occurrences['record'].append({
        'office': 'PHX',
        'state': 'AZ',
        'text': 'record high temperatures expected this weekend'
    })
    
    keyword_occurrences['ice'].append({
        'office': 'SLC',
        'state': 'UT',
        'text': 'ice conditions hazardous for travel'
    })
    
    keyword_occurrences['snow'].append({
        'office': 'DEN',
        'state': 'CO',
        'text': 'snow conditions remain hazardous'
    })
    
    keyword_occurrences['thunderstorm'].append({
        'office': 'BOU',
        'state': 'CO',
        'text': 'thunderstorm activity expected through evening'
    })
    
    keyword_occurrences['shortwave'].append({
        'office': 'FOC',
        'state': 'AK',
        'text': 'shortwave disturbances moving through the area'
    })
    
    keyword_occurrences['surface low'].append({
        'office': 'GLD',
        'state': 'KS',
        'text': 'surface low pressure developing in the plains'
    })
    
    keyword_occurrences['trough'].append({
        'office': 'ICT',
        'state': 'KS',
        'text': 'troughs of low pressure bringing precipitation'
    })
    
    return {
        'summaries': {
            'AK': {
                'ANC': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=ANC&issuedby=ANC&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'dryline': 1, 'ice': 1, 'snow': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'CO': {
                'BOU': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=BOU&issuedby=BOU&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'dryline': 1, 'thunderstorm': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                },
                'DEN': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=DEN&issuedby=DEN&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'snow': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'TX': {
                'DMX': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=DMX&issuedby=DMX&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'severe': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'NM': {
                'ABQ': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=ABQ&issuedby=ABQ&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'front': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'AZ': {
                'PHX': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=PHX&issuedby=PHX&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'record': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'UT': {
                'SLC': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=SLC&issuedby=SLC&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'ice': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'KS': {
                'GLD': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=GLD&issuedby=GLD&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'surface low': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                },
                'ICT': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=ICT&issuedby=ICT&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'trough': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            },
            'AK': {
                'FOC': {
                    'full_text': MOCK_DATA,
                    'url': 'https://forecast.weather.gov/product.php?site=FOC&issuedby=FOC&product=AFD&format=txt&version=1&glossary=0',
                    'keyword_summary': MOCK_DATA.split('\n')[2],
                    'keyword_counts': {'shortwave': 1},
                    'ai_summary': get_ai_summary(MOCK_DATA)
                }
            }
        },
        'keyword_map': {
            'dryline': ['AK', 'CO'],
            'severe': ['TX'],
            'front': ['NM'],
            'record': ['AZ'],
            'ice': ['UT'],
            'snow': ['CO'],
            'thunderstorm': ['CO'],
            'shortwave': ['AK'],
            'surface low': ['KS'],
            'trough': ['KS']
        },
        'keyword_counts': {
            'dryline': 2,
            'severe': 1,
            'front': 1,
            'record': 1,
            'ice': 1,
            'snow': 1,
            'thunderstorm': 1,
            'shortwave': 1,
            'surface low': 1,
            'trough': 1
        },
        'keyword_occurrences': keyword_occurrences,
        'map_html': '<div id="map">Mock Map</div>',
        'base_url': 'https://forecast.weather.gov/product.php?site='
    }

def test_keyword_summary():
    """Test the keyword summary generation."""
    print("=" * 60)
    print("Testing Keyword Summary Generation")
    print("=" * 60)
    
    mock_data = create_mock_processed_data()
    
    html = generate_keyword_summary(
        mock_data['keyword_map'],
        mock_data['keyword_counts'],
        mock_data['keyword_occurrences']
    )
    
    print("\nKeyword Summary HTML:")
    print(html)
    return html

def test_office_summaries():
    """Test the office summaries generation."""
    print("\n" + "=" * 60)
    print("Testing Office Summaries Generation")
    print("=" * 60)
    
    mock_data = create_mock_processed_data()
    
    html = generate_office_summaries(mock_data['summaries'])
    
    print("\nOffice Summaries HTML (first 2000 chars):")
    print(html[:2000])
    return html

def test_full_dashboard():
    """Test the full dashboard generation."""
    print("\n" + "=" * 60)
    print("Testing Full Dashboard Generation")
    print("=" * 60)
    
    mock_data = create_mock_processed_data()
    
    html = generate_dashboard_html(
        mock_data,
        "2026-03-31 23:30:00 UTC",
        "v2.0 - AI Enhanced"
    )
    
    print(f"\nDashboard HTML length: {len(html)} characters")
    print(f"Dashboard HTML preview (first 1000 chars):")
    print(html[:1000])
    return html

if __name__ == '__main__':
    test_keyword_summary()
    print("\n" + "=" * 60)
    test_office_summaries()
    print("\n" + "=" * 60)
    test_full_dashboard()
    print("\n✓ All tests completed!")
