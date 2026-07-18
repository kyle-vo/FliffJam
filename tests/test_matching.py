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
        
        target_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]
        
        sharp_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(target_markets, sharp_markets)
        
        assert len(matches) == 1
        assert matches[0]['target']['player'] == 'LeBron James'
        assert matches[0]['sharp']['player'] == 'LeBron James'
        assert matches[0]['match_score'] == 100.0
    
    def test_fuzzy_match(self):
        """Test matching with similar but not identical names."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        target_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]
        
        sharp_markets = [{
            'player': 'Lebron James',  # Different capitalization
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(target_markets, sharp_markets)
        
        assert len(matches) == 1
        assert matches[0]['match_score'] >= 80.0
    
    def test_no_match_different_player(self):
        """Test no match when players are completely different."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        target_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]
        
        sharp_markets = [{
            'player': 'Stephen Curry',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(target_markets, sharp_markets)
        
        assert len(matches) == 0
    
    def test_no_match_different_selection(self):
        """Test no match when selections differ (Over vs Under)."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        target_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]
        
        sharp_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Under',  # Different selection
            'line': 25.5,
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(target_markets, sharp_markets)
        
        assert len(matches) == 0
    
    def test_line_tolerance(self):
        """Test matching respects line tolerance."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        target_markets = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]
        
        # Within tolerance
        sharp_markets_close = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.0,  # 0.5 difference - within tolerance
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(target_markets, sharp_markets_close)
        assert len(matches) == 1
        
        # Outside tolerance
        sharp_markets_far = [{
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 24.0,  # 1.5 difference - outside tolerance
            'american_odds': -105,
            'decimal_odds': 1.952
        }]
        
        matches = matcher.match_markets(target_markets, sharp_markets_far)
        assert len(matches) == 0
    
    def test_find_two_sided_pairs(self):
        """Test finding Over/Under pairs."""
        matcher = MarketMatcher()
        
        markets = [
            {
                'bookmaker': 'pinnacle',
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            {
                'bookmaker': 'pinnacle',
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Under',
                'line': 25.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            {
                'bookmaker': 'pinnacle',
                'player': 'Stephen Curry',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 28.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            },
            # Missing Under for Curry - should not create pair.
            # DraftKings has Curry's Under — but a pair must never mix books.
            {
                'bookmaker': 'draftkings',
                'player': 'Stephen Curry',
                'market_key': 'player_points',
                'selection': 'Under',
                'line': 28.5,
                'american_odds': -115,
                'decimal_odds': 1.870
            }
        ]

        pairs = matcher.find_two_sided_pairs(markets)

        # Should find only LeBron's complete same-book pair
        assert len(pairs) == 1
        assert pairs[0]['player'] == 'LeBron James'
        assert pairs[0]['bookmaker'] == 'pinnacle'
        assert 'over' in pairs[0]
        assert 'under' in pairs[0]
        assert pairs[0]['line'] == 25.5

    def test_sharp_priority_prefers_pinnacle(self):
        """When several sharp books carry the line, Pinnacle wins."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)

        target_markets = [{
            'bookmaker': 'kalshi',
            'player': 'LeBron James',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]

        sharp_markets = [
            {
                'bookmaker': 'fanduel',
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -102,
                'decimal_odds': 1.980
            },
            {
                'bookmaker': 'pinnacle',
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            }
        ]

        matches = matcher.match_markets(target_markets, sharp_markets)

        assert len(matches) == 1
        assert matches[0]['sharp']['bookmaker'] == 'pinnacle'

    def test_sharp_fallback_when_pinnacle_missing(self):
        """Falls back to the next sharp book when Pinnacle lacks the line."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)

        target_markets = [{
            'bookmaker': 'prizepicks',
            'player': 'Stephen Curry',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 28.5,
            'american_odds': -119,
            'decimal_odds': 1.840
        }]

        sharp_markets = [{
            'bookmaker': 'fanduel',
            'player': 'Stephen Curry',
            'market_key': 'player_points',
            'selection': 'Over',
            'line': 28.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }]

        matches = matcher.match_markets(target_markets, sharp_markets)

        assert len(matches) == 1
        assert matches[0]['sharp']['bookmaker'] == 'fanduel'
    
    def test_multiple_matches(self):
        """Test matching multiple markets."""
        matcher = MarketMatcher(similarity_threshold=80.0, line_tolerance=0.5)
        
        target_markets = [
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
        
        sharp_markets = [
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
        
        matches = matcher.match_markets(target_markets, sharp_markets)
        
        assert len(matches) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
