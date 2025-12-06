"""
Market matching utilities using fuzzy string matching.
Matches Fliff markets with Pinnacle markets based on player name, line, and selection.
"""
import logging
from typing import List, Dict, Optional
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)


class MarketMatcher:
    """Matches betting markets between two bookmakers."""
    
    def __init__(self, similarity_threshold: float = 80.0, line_tolerance: float = 0.5):
        """
        Initialize matcher.
        
        Args:
            similarity_threshold: Minimum fuzzy match score (0-100) for player names
            line_tolerance: Maximum allowed difference in line values
        """
        self.similarity_threshold = similarity_threshold
        self.line_tolerance = line_tolerance
    
    def match_markets(
        self,
        fliff_markets: List[Dict],
        pinnacle_markets: List[Dict]
    ) -> List[Dict]:
        """
        Match Fliff markets with corresponding Pinnacle markets.
        
        Returns list of matched pairs:
        {
            'fliff': {...},
            'pinnacle': {...},
            'match_score': 95.5
        }
        """
        matches = []
        
        # Group Pinnacle markets by market_key for faster lookup
        pinnacle_by_market = {}
        for market in pinnacle_markets:
            market_key = market.get('market_key', '')
            if market_key not in pinnacle_by_market:
                pinnacle_by_market[market_key] = []
            pinnacle_by_market[market_key].append(market)
        
        for fliff_market in fliff_markets:
            match = self._find_best_match(fliff_market, pinnacle_by_market)
            if match:
                matches.append(match)
        
        logger.info(f"Matched {len(matches)} markets out of {len(fliff_markets)} Fliff markets")
        return matches
    
    def _find_best_match(
        self,
        fliff_market: Dict,
        pinnacle_by_market: Dict[str, List[Dict]]
    ) -> Optional[Dict]:
        """Find best matching Pinnacle market for a Fliff market."""
        market_key = fliff_market.get('market_key', '')
        fliff_player = fliff_market.get('player', '')
        fliff_selection = fliff_market.get('selection', '')
        fliff_line = fliff_market.get('line')
        
        # Get candidate Pinnacle markets with same market type
        candidates = pinnacle_by_market.get(market_key, [])
        if not candidates:
            return None
        
        # Filter candidates by selection type (Over/Under)
        if fliff_selection:
            candidates = [
                c for c in candidates 
                if c.get('selection', '').lower() == fliff_selection.lower()
            ]
        
        if not candidates:
            return None
        
        # Find best player name match
        best_match = None
        best_score = 0
        
        for candidate in candidates:
            pinnacle_player = candidate.get('player', '')
            pinnacle_line = candidate.get('line')
            
            # Calculate player name similarity
            name_score = fuzz.ratio(
                fliff_player.lower(),
                pinnacle_player.lower()
            )
            
            if name_score < self.similarity_threshold:
                continue
            
            # Check line tolerance if both have lines
            if fliff_line is not None and pinnacle_line is not None:
                line_diff = abs(fliff_line - pinnacle_line)
                if line_diff > self.line_tolerance:
                    continue
            
            # Use name score as match quality
            if name_score > best_score:
                best_score = name_score
                best_match = candidate
        
        if best_match:
            return {
                'fliff': fliff_market,
                'pinnacle': best_match,
                'match_score': best_score
            }
        
        return None
    
    def find_two_sided_pairs(self, markets: List[Dict], bookmaker: str) -> List[Dict]:
        """
        Find Over/Under pairs for the same market to enable vig removal.
        
        Args:
            markets: List of markets from one bookmaker
            bookmaker: 'fliff' or 'pinnacle'
        
        Returns:
            List of paired markets:
            {
                'market_key': 'player_points',
                'player': 'LeBron James',
                'line': 25.5,
                'over': {...},
                'under': {...}
            }
        """
        pairs = []
        
        # Group by (player, market_key, line)
        market_groups = {}
        for market in markets:
            key = (
                market.get('player', ''),
                market.get('market_key', ''),
                market.get('line')
            )
            
            if key not in market_groups:
                market_groups[key] = {}
            
            selection = market.get('selection', '').lower()
            market_groups[key][selection] = market
        
        # Find complete pairs
        for key, selections in market_groups.items():
            if 'over' in selections and 'under' in selections:
                player, market_key, line = key
                pairs.append({
                    'bookmaker': bookmaker,
                    'market_key': market_key,
                    'player': player,
                    'line': line,
                    'over': selections['over'],
                    'under': selections['under']
                })
        
        logger.info(f"Found {len(pairs)} two-sided pairs for {bookmaker}")
        return pairs


def match_markets(
    fliff_markets: List[Dict],
    pinnacle_markets: List[Dict],
    similarity_threshold: float = 80.0,
    line_tolerance: float = 0.5
) -> List[Dict]:
    """Convenience function to match markets."""
    matcher = MarketMatcher(similarity_threshold, line_tolerance)
    return matcher.match_markets(fliff_markets, pinnacle_markets)
