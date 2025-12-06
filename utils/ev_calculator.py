"""
EV (Expected Value) calculation utilities.
Includes vig removal for two-sided markets and EV computation.
"""
import logging
from typing import Dict, List, Optional
import math

logger = logging.getLogger(__name__)


class EVCalculator:
    """Calculate expected value for betting markets."""
    
    @staticmethod
    def american_to_decimal(american_odds: int) -> float:
        """Convert American odds to decimal odds."""
        if american_odds > 0:
            return (american_odds / 100.0) + 1.0
        else:
            return (100.0 / abs(american_odds)) + 1.0
    
    @staticmethod
    def decimal_to_implied_prob(decimal_odds: float) -> float:
        """Convert decimal odds to implied probability."""
        return 1.0 / decimal_odds
    
    @staticmethod
    def remove_vig_multiplicative(over_decimal: float, under_decimal: float) -> Dict[str, float]:
        """
        Remove vig using multiplicative method (most common).
        
        Returns:
            {
                'over_true_prob': 0.52,
                'under_true_prob': 0.48,
                'vig_removed': 0.04
            }
        """
        over_implied = 1.0 / over_decimal
        under_implied = 1.0 / under_decimal
        total_implied = over_implied + under_implied
        
        # Vig is the amount over 100%
        vig = total_implied - 1.0
        
        # Remove vig proportionally
        over_true_prob = over_implied / total_implied
        under_true_prob = under_implied / total_implied
        
        return {
            'over_true_prob': over_true_prob,
            'under_true_prob': under_true_prob,
            'vig_removed': vig
        }
    
    @staticmethod
    def calculate_ev(bet_decimal_odds: float, true_probability: float) -> float:
        """
        Calculate expected value per $1 bet.
        
        EV = (decimal_odds * true_probability) - 1.0
        
        Args:
            bet_decimal_odds: Decimal odds offered on the bet
            true_probability: True probability of outcome (after vig removal)
        
        Returns:
            EV per $1 wagered (e.g., 0.05 = 5% expected return)
        """
        return (bet_decimal_odds * true_probability) - 1.0
    
    @staticmethod
    def calculate_ev_percentage(bet_decimal_odds: float, true_probability: float) -> float:
        """Calculate EV as a percentage."""
        return EVCalculator.calculate_ev(bet_decimal_odds, true_probability) * 100
    
    def process_matched_market(self, matched_pair: Dict) -> Optional[Dict]:
        """
        Process a matched market pair to calculate EV.
        
        Args:
            matched_pair: Dict with 'fliff' and 'pinnacle' markets
        
        Returns:
            {
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'fliff_odds': -110,
                'fliff_decimal': 1.909,
                'pinnacle_odds': -105,
                'pinnacle_decimal': 1.952,
                'true_probability': 0.52,
                'ev': 0.0087,
                'ev_percent': 0.87
            }
        """
        fliff = matched_pair.get('fliff', {})
        pinnacle = matched_pair.get('pinnacle', {})
        
        if not fliff or not pinnacle:
            return None
        
        return {
            'player': fliff.get('player', ''),
            'event': fliff.get('event', ''),
            'market_key': fliff.get('market_key', ''),
            'selection': fliff.get('selection', ''),
            'line': fliff.get('line'),
            'fliff_odds': fliff.get('american_odds'),
            'fliff_decimal': fliff.get('decimal_odds'),
            'pinnacle_odds': pinnacle.get('american_odds'),
            'pinnacle_decimal': pinnacle.get('decimal_odds'),
            'match_score': matched_pair.get('match_score', 0)
        }
    
    def calculate_ev_with_pairs(
        self,
        matched_markets: List[Dict],
        pinnacle_pairs: List[Dict]
    ) -> List[Dict]:
        """
        Calculate EV for matched markets using Pinnacle pairs for vig removal.
        
        Args:
            matched_markets: List of matched Fliff/Pinnacle markets
            pinnacle_pairs: List of Pinnacle over/under pairs
        
        Returns:
            List of markets with EV calculations
        """
        results = []
        
        # Create lookup for Pinnacle pairs
        pair_lookup = {}
        for pair in pinnacle_pairs:
            key = (pair['player'], pair['market_key'], pair['line'])
            pair_lookup[key] = pair
        
        for matched in matched_markets:
            processed = self.process_matched_market(matched)
            if not processed:
                continue
            
            # Try to find corresponding Pinnacle pair for vig removal
            lookup_key = (
                processed['player'],
                processed['market_key'],
                processed['line']
            )
            
            pinnacle_pair = pair_lookup.get(lookup_key)
            
            if pinnacle_pair:
                # We have a two-sided market - remove vig
                over_decimal = pinnacle_pair['over']['decimal_odds']
                under_decimal = pinnacle_pair['under']['decimal_odds']
                
                vig_removed = self.remove_vig_multiplicative(over_decimal, under_decimal)
                
                # Determine which probability to use based on selection
                selection = processed['selection'].lower()
                if selection == 'over':
                    true_prob = vig_removed['over_true_prob']
                elif selection == 'under':
                    true_prob = vig_removed['under_true_prob']
                else:
                    # Fallback to implied probability from Pinnacle
                    true_prob = self.decimal_to_implied_prob(processed['pinnacle_decimal'])
                
                processed['vig_removed'] = vig_removed['vig_removed']
            else:
                # No pair found - use Pinnacle implied probability as-is
                # This is less accurate but better than nothing
                true_prob = self.decimal_to_implied_prob(processed['pinnacle_decimal'])
                processed['vig_removed'] = None
                logger.debug(f"No pair found for {processed['player']} {processed['market_key']}")
            
            # Calculate EV
            processed['true_probability'] = true_prob
            processed['ev'] = self.calculate_ev(processed['fliff_decimal'], true_prob)
            processed['ev_percent'] = processed['ev'] * 100
            
            results.append(processed)
        
        # Sort by EV descending
        results.sort(key=lambda x: x['ev'], reverse=True)
        
        logger.info(f"Calculated EV for {len(results)} markets")
        positive_ev = [r for r in results if r['ev'] > 0]
        logger.info(f"Found {len(positive_ev)} positive EV opportunities")
        
        return results


def calculate_ev_from_data(
    fliff_markets: List[Dict],
    pinnacle_markets: List[Dict],
    matched_markets: List[Dict]
) -> List[Dict]:
    """
    Convenience function to calculate EV from fetched data.
    
    Args:
        fliff_markets: Raw Fliff markets
        pinnacle_markets: Raw Pinnacle markets  
        matched_markets: Already matched market pairs
    
    Returns:
        List of markets with EV calculations sorted by EV descending
    """
    from .matching import MarketMatcher
    
    calculator = EVCalculator()
    matcher = MarketMatcher()
    
    # Find Pinnacle two-sided pairs for vig removal
    pinnacle_pairs = matcher.find_two_sided_pairs(pinnacle_markets, 'pinnacle')
    
    # Calculate EV
    return calculator.calculate_ev_with_pairs(matched_markets, pinnacle_pairs)
