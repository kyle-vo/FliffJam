"""
Tests for market matching utilities.
"""
import pytest
from utils.matching import MarketMatcher


class TestMarketMatcher:
    """Test market matching functions."""
    
    def test_exact_match(self):
        """Test matching with identical player names."""
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
        assert matches[0]['fliff']['player'] == 'LeBron James'
        assert matches[0]['pinnacle']['player'] == 'LeBron James'
        assert matches[0]['match_score'] == 100.0
    
    def test_fuzzy_match(self):
        """Test matching with similar but not identical names."""
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
            'player': 'Lebron James',  # Different capitalization
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(fliff_markets, pinnacle_markets)
        
        assert len(matches) == 1
        assert matches[0]['match_score'] >= 80.0
    
    def test_no_match_different_player(self):
        """Test no match when players are completely different."""
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
            'player': 'Stephen Curry',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(fliff_markets, pinnacle_markets)
        
        assert len(matches) == 0
    
    def test_no_match_different_selection(self):
        """Test no match when selections differ (Over vs Under)."""
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
            'selection': 'Under',  # Different selection
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(fliff_markets, pinnacle_markets)
        
        assert len(matches) == 0
    
    def test_line_tolerance(self):
        """Test matching respects line tolerance."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        fliff_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]
        
        # Within tolerance
        pinnacle_markets_close = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.0,  # 0.5 difference - within tolerance
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(fliff_markets, pinnacle_markets_close)
        assert len(matches) == 1
        
        # Outside tolerance
        pinnacle_markets_far = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 24.0,  # 1.5 difference - outside tolerance
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(fliff_markets, pinnacle_markets_far)
        assert len(matches) == 0
    
    def test_find_two_sided_pairs(self):
        """Test finding Over/Under pairs."""
        matcher = MarketMatcher()
        
        markets = [
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
            },
            {
                'player': 'Stephen Curry',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 28.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            }
            # Missing Under for Curry - should not create pair
        ]
        
        pairs = matcher.find_two_sided_pairs(markets, 'pinnacle')
        
        # Should find only LeBron's complete pair
        assert len(pairs) == 1
        assert pairs[0]['player'] == 'LeBron James'
        assert 'over' in pairs[0]
        assert 'under' in pairs[0]
        assert pairs[0]['line'] == 25.5
    
    def test_multiple_matches(self):
        """Test matching multiple markets."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        fliff_markets = [
            {
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            {
                'player': 'Stephen Curry',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 28.5,
                'american_odds': -115,
                'decimal_odds': 1.870
            }
        ]
        
        pinnacle_markets = [
            {
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            },
            {
                'player': 'Stephen Curry',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 28.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            }
        ]
        
        matches = matcher.match_markets(fliff_markets, pinnacle_markets)
        
        assert len(matches) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
