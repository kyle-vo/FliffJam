"""
Tests for EV calculator utilities.
"""
import pytest
from utils.ev_calculator import EVCalculator


class TestEVCalculator:
    """Test EV calculation functions."""
    
    def test_american_to_decimal_positive(self):
        """Test converting positive American odds to decimal."""
        calc = EVCalculator()
        assert calc.american_to_decimal(100) == 2.0
        assert calc.american_to_decimal(150) == 2.5
        assert calc.american_to_decimal(200) == 3.0
    
    def test_american_to_decimal_negative(self):
        """Test converting negative American odds to decimal."""
        calc = EVCalculator()
        assert abs(calc.american_to_decimal(-110) - 1.909) < 0.01
        assert abs(calc.american_to_decimal(-150) - 1.667) < 0.01
        assert calc.american_to_decimal(-100) == 2.0
    
    def test_decimal_to_implied_prob(self):
        """Test converting decimal odds to implied probability."""
        calc = EVCalculator()
        assert abs(calc.decimal_to_implied_prob(2.0) - 0.5) < 0.001
        assert abs(calc.decimal_to_implied_prob(4.0) - 0.25) < 0.001
        assert abs(calc.decimal_to_implied_prob(1.5) - 0.667) < 0.01
    
    def test_remove_vig_multiplicative(self):
        """Test vig removal from two-sided market."""
        calc = EVCalculator()
        
        # Standard -110/-110 market
        result = calc.remove_vig_multiplicative(1.909, 1.909)
        
        assert abs(result['over_true_prob'] - 0.5) < 0.01
        assert abs(result['under_true_prob'] - 0.5) < 0.01
        assert result['vig_removed'] > 0
        assert abs(result['over_true_prob'] + result['under_true_prob'] - 1.0) < 0.001
    
    def test_remove_vig_asymmetric(self):
        """Test vig removal with different odds."""
        calc = EVCalculator()
        
        # Over at -120, Under at +100
        over_decimal = calc.american_to_decimal(-120)  # ~1.833
        under_decimal = calc.american_to_decimal(100)   # 2.0
        
        result = calc.remove_vig_multiplicative(over_decimal, under_decimal)
        
        # Should still sum to 1.0
        assert abs(result['over_true_prob'] + result['under_true_prob'] - 1.0) < 0.001
        
        # Over should have higher true probability (it's favored)
        assert result['over_true_prob'] > result['under_true_prob']
    
    def test_calculate_ev_positive(self):
        """Test EV calculation for positive EV bet."""
        calc = EVCalculator()
        
        # Bet at +100 (2.0 decimal) with 55% true probability
        ev = calc.calculate_ev(2.0, 0.55)
        
        # EV = 2.0 * 0.55 - 1.0 = 0.10 (10%)
        assert abs(ev - 0.10) < 0.001
    
    def test_calculate_ev_negative(self):
        """Test EV calculation for negative EV bet."""
        calc = EVCalculator()
        
        # Bet at +100 (2.0 decimal) with 45% true probability
        ev = calc.calculate_ev(2.0, 0.45)
        
        # EV = 2.0 * 0.45 - 1.0 = -0.10 (-10%)
        assert abs(ev - (-0.10)) < 0.001
    
    def test_calculate_ev_break_even(self):
        """Test EV calculation for break-even bet."""
        calc = EVCalculator()
        
        # Bet at +100 (2.0 decimal) with 50% true probability
        ev = calc.calculate_ev(2.0, 0.50)
        
        # EV = 2.0 * 0.50 - 1.0 = 0.0
        assert abs(ev) < 0.001
    
    def test_calculate_ev_percentage(self):
        """Test EV percentage calculation."""
        calc = EVCalculator()
        
        ev_pct = calc.calculate_ev_percentage(2.0, 0.55)
        
        assert abs(ev_pct - 10.0) < 0.1
    
    def test_process_matched_market(self):
        """Test processing a matched market pair."""
        calc = EVCalculator()
        
        matched_pair = {
            'target': {
                'player': 'LeBron James',
                'event': 'Lakers vs Warriors',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            'sharp': {
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            },
            'match_score': 95.5
        }
        
        result = calc.process_matched_market(matched_pair)
        
        assert result is not None
        assert result['player'] == 'LeBron James'
        assert result['line'] == 25.5
        assert result['target_odds'] == -110
        assert result['sharp_odds'] == -105
        assert result['match_score'] == 95.5


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
