"""Simple test runner that doesn't require pytest."""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.ev_calculator import EVCalculator
from utils.matching import MarketMatcher

def test_ev_calculator():
    """Test basic EV calculations."""
    print("Testing EV Calculator...")
    calc = EVCalculator()
    
    # Test American to decimal conversion
    assert abs(calc.american_to_decimal(100) - 2.0) < 0.001
    assert abs(calc.american_to_decimal(-110) - 1.909) < 0.01
    print("✓ American to decimal conversion works")
    
    # Test EV calculation
    ev = calc.calculate_ev(2.0, 0.55)
    assert abs(ev - 0.10) < 0.001
    print("✓ EV calculation works")
    
    # Test vig removal
    result = calc.remove_vig_multiplicative(1.909, 1.909)
    assert abs(result['over_true_prob'] - 0.5) < 0.01
    assert abs(result['under_true_prob'] - 0.5) < 0.01
    print("✓ Vig removal works")
    
    print("✅ All EV Calculator tests passed!\n")

def test_market_matcher():
    """Test market matching logic."""
    print("Testing Market Matcher...")
    matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
    
    fliff_markets = [{
        'player': 'LeBron James',
        'market_key': 'player_points',
        'selection': 'Over',
        'line': 25.5,
        'american_odds': -110,
        'decimal_odds': 1.909
    }]
    
    pinnacle_markets = [{
        'player': 'LeBron James',
        'market_key': 'player_points',
        'selection': 'Over',
        'line': 25.5,
        'american_odds': -105,
        'decimal_odds': 1.952
    }]
    
    matches = matcher.match_markets(fliff_markets, pinnacle_markets)
    assert len(matches) == 1
    assert matches[0]['match_score'] == 100.0
    print("✓ Exact matching works")
    
    # Test no match with different players
    pinnacle_markets_diff = [{
        'player': 'Stephen Curry',
        'market_key': 'player_points',
        'selection': 'Over',
        'line': 25.5,
        'american_odds': -105,
        'decimal_odds': 1.952
    }]
    
    matches = matcher.match_markets(fliff_markets, pinnacle_markets_diff)
    assert len(matches) == 0
    print("✓ Different players don't match")
    
    # Test two-sided pairs
    two_sided = [
        {
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        },
        {
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Under',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }
    ]
    
    pairs = matcher.find_two_sided_pairs(two_sided, 'pinnacle')
    assert len(pairs) == 1
    assert pairs[0]['player'] == 'LeBron James'
    print("✓ Two-sided pair detection works")
    
    print("✅ All Market Matcher tests passed!\n")

if __name__ == '__main__':
    try:
        test_ev_calculator()
        test_market_matcher()
        print("=" * 50)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 50)
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
