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
            matched_pair: Dict with 'target' and 'sharp' markets

        Returns:
            {
                'player': 'LeBron James',
                'market_key': 'player_points',
                'selection': 'Over',
                'line': 25.5,
                'target_book': 'kalshi',
                'target_odds': -110,
                'target_decimal': 1.909,
                'sharp_book': 'pinnacle',
                'sharp_odds': -105,
                'sharp_decimal': 1.952,
                'true_probability': 0.52,
                'ev': 0.0087,
                'ev_percent': 0.87
            }
        """
        target = matched_pair.get('target', {})
        sharp = matched_pair.get('sharp', {})

        if not target or not sharp:
            return None

        return {
            'player': target.get('player', ''),
            'event': target.get('event', ''),
            'market_key': target.get('market_key', ''),
            'selection': target.get('selection', ''),
            'line': target.get('line'),
            'sport': target.get('sport', ''),
            'target_book': target.get('bookmaker', ''),
            'target_odds': target.get('american_odds'),
            'target_decimal': target.get('decimal_odds'),
            'sharp_book': sharp.get('bookmaker', ''),
            'sharp_odds': sharp.get('american_odds'),
            'sharp_decimal': sharp.get('decimal_odds'),
            'sharp_line': sharp.get('line'),
            'match_score': matched_pair.get('match_score', 0)
        }
    
    def calculate_ev_with_pairs(
        self,
        matched_markets: List[Dict],
        sharp_pairs: List[Dict]
    ) -> List[Dict]:
        """
        Calculate EV for matched markets using sharp-book pairs for vig removal.

        Args:
            matched_markets: List of matched target/sharp markets
            sharp_pairs: List of sharp-book over/under pairs (per bookmaker)

        Returns:
            List of markets with EV calculations
        """
        results = []

        # Create lookup for sharp pairs — keyed per bookmaker so vig removal
        # always uses the same book the market was matched against
        pair_lookup = {}
        for pair in sharp_pairs:
            key = (pair['bookmaker'], pair['player'], pair['market_key'], pair['line'])
            pair_lookup[key] = pair

        for matched in matched_markets:
            processed = self.process_matched_market(matched)
            if not processed:
                continue

            # Look up the matched sharp book's own over/under pair. Use the
            # sharp market's line (it can differ from the target line within
            # tolerance) and its player spelling via the sharp market itself.
            sharp_market = matched.get('sharp', {})
            lookup_key = (
                processed['sharp_book'],
                sharp_market.get('player', processed['player']),
                processed['market_key'],
                sharp_market.get('line', processed['line'])
            )

            sharp_pair = pair_lookup.get(lookup_key)

            if sharp_pair:
                # We have a two-sided market - remove vig
                over_decimal = sharp_pair['over']['decimal_odds']
                under_decimal = sharp_pair['under']['decimal_odds']

                vig_removed = self.remove_vig_multiplicative(over_decimal, under_decimal)

                # Determine which probability to use based on selection
                selection = processed['selection'].lower()
                if selection == 'over':
                    true_prob = vig_removed['over_true_prob']
                elif selection == 'under':
                    true_prob = vig_removed['under_true_prob']
                else:
                    # Fallback to implied probability from the sharp book
                    true_prob = self.decimal_to_implied_prob(processed['sharp_decimal'])

                processed['vig_removed'] = vig_removed['vig_removed']
            else:
                # No pair found - use sharp implied probability as-is
                # This is less accurate but better than nothing
                true_prob = self.decimal_to_implied_prob(processed['sharp_decimal'])
                processed['vig_removed'] = None
                logger.debug(f"No pair found for {processed['player']} {processed['market_key']}")

            # Calculate EV
            processed['true_probability'] = true_prob
            processed['ev'] = self.calculate_ev(processed['target_decimal'], true_prob)
            processed['ev_percent'] = processed['ev'] * 100

            results.append(processed)
        
        # Sort by EV descending
        results.sort(key=lambda x: x['ev'], reverse=True)
        
        logger.info(f"Calculated EV for {len(results)} markets")
        positive_ev = [r for r in results if r['ev'] > 0]
        logger.info(f"Found {len(positive_ev)} positive EV opportunities")
        
        return results


    def calculate_ev_multi(
        self,
        matched_multi: List[Dict],
        sharp_pairs: List[Dict]
    ) -> List[Dict]:
        """
        EV for multi-book matches. De-vigs against the sharpest available book
        (SHARP_PRIORITY order) for the "true" probability, but carries every
        matched book's price in `sharp_odds_by_book` for a side-by-side display.
        """
        from .matching import SHARP_PRIORITY

        results = []

        pair_lookup = {}
        for pair in sharp_pairs:
            key = (pair['bookmaker'], pair['player'], pair['market_key'], pair['line'])
            pair_lookup[key] = pair

        for matched in matched_multi:
            target = matched.get('target', {})
            sharps = matched.get('sharps', {})
            if not target or not sharps:
                continue

            # Pick the sharpest book present for the true-probability reference
            ref_book = next((b for b in SHARP_PRIORITY if b in sharps), None)
            if ref_book is None:
                ref_book = sorted(sharps.keys())[0]
            ref = sharps[ref_book]

            # Prices from every matched book, for display
            sharp_odds_by_book = {
                book: {
                    'odds': m.get('american_odds'),
                    'decimal': m.get('decimal_odds'),
                    'line': m.get('line'),
                }
                for book, m in sharps.items()
            }

            # De-vig the reference book's own over/under pair
            lookup_key = (ref_book, ref.get('player', ''), ref.get('market_key', ''), ref.get('line'))
            sharp_pair = pair_lookup.get(lookup_key)

            selection = target.get('selection', '').lower()
            if sharp_pair:
                vig_removed = self.remove_vig_multiplicative(
                    sharp_pair['over']['decimal_odds'],
                    sharp_pair['under']['decimal_odds']
                )
                if selection == 'over':
                    true_prob = vig_removed['over_true_prob']
                elif selection == 'under':
                    true_prob = vig_removed['under_true_prob']
                else:
                    true_prob = self.decimal_to_implied_prob(ref.get('decimal_odds'))
                vig = vig_removed['vig_removed']
            else:
                true_prob = self.decimal_to_implied_prob(ref.get('decimal_odds'))
                vig = None

            target_decimal = target.get('decimal_odds')
            ev = self.calculate_ev(target_decimal, true_prob)

            results.append({
                'player': target.get('player', ''),
                'event': target.get('event', ''),
                'market_key': target.get('market_key', ''),
                'selection': target.get('selection', ''),
                'line': target.get('line'),
                'sport': target.get('sport', ''),
                'target_book': target.get('bookmaker', ''),
                'target_odds': target.get('american_odds'),
                'target_decimal': target_decimal,
                'sharp_book': ref_book,           # book used for the EV/true prob
                'sharp_odds': ref.get('american_odds'),
                'sharp_decimal': ref.get('decimal_odds'),
                'sharp_odds_by_book': sharp_odds_by_book,
                'true_probability': true_prob,
                'vig_removed': vig,
                'ev': ev,
                'ev_percent': ev * 100,
                'match_score': matched.get('match_score', 0)
            })

        results.sort(key=lambda x: x['ev'], reverse=True)
        positive = [r for r in results if r['ev'] > 0]
        logger.info(f"Multi-book EV: {len(positive)} positive of {len(results)} total")
        return results


def calculate_ev_multi_from_data(
    target_markets: List[Dict],
    sharp_markets: List[Dict],
    matched_multi: List[Dict]
) -> List[Dict]:
    """Convenience wrapper for the multi-book EV path."""
    from .matching import MarketMatcher

    calculator = EVCalculator()
    matcher = MarketMatcher()
    sharp_pairs = matcher.find_two_sided_pairs(sharp_markets)
    return calculator.calculate_ev_multi(matched_multi, sharp_pairs)


def calculate_ev_from_data(
    target_markets: List[Dict],
    sharp_markets: List[Dict],
    matched_markets: List[Dict]
) -> List[Dict]:
    """
    Convenience function to calculate EV from fetched data.

    Args:
        target_markets: Raw target-book markets (kalshi, prizepicks)
        sharp_markets: Raw sharp-book markets (pinnacle, draftkings, fanduel)
        matched_markets: Already matched market pairs

    Returns:
        List of markets with EV calculations sorted by EV descending
    """
    from .matching import MarketMatcher

    calculator = EVCalculator()
    matcher = MarketMatcher()

    # Find sharp-book two-sided pairs (per bookmaker) for vig removal
    sharp_pairs = matcher.find_two_sided_pairs(sharp_markets)

    # Calculate EV
    return calculator.calculate_ev_with_pairs(matched_markets, sharp_pairs)
