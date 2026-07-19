"""
Market matching utilities using fuzzy string matching.
Matches target-book markets (kalshi, prizepicks) with sharp-book markets
(pinnacle, draftkings, fanduel) based on player name, line, and selection.
"""
import logging
from typing import List, Dict, Optional
from rapidfuzz import fuzz, process

logger = logging.getLogger(__name__)

# Priority order when several sharp books carry the same line — Pinnacle is
# the sharpest reference, so prefer it, then fall back down the list.
SHARP_PRIORITY = ['pinnacle', 'draftkings', 'fanduel']


class MarketMatcher:
    """Matches betting markets between target and sharp bookmakers."""

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
        target_markets: List[Dict],
        sharp_markets: List[Dict]
    ) -> List[Dict]:
        """
        Match target-book markets with corresponding sharp-book markets.

        Returns list of matched pairs:
        {
            'target': {...},
            'sharp': {...},
            'match_score': 95.5
        }
        """
        matches = []

        # Group sharp markets by (market_key, bookmaker) for prioritized lookup
        sharp_by_market = {}
        for market in sharp_markets:
            key = (market.get('market_key', ''), market.get('bookmaker', ''))
            sharp_by_market.setdefault(key, []).append(market)

        for target_market in target_markets:
            match = self._find_best_match(target_market, sharp_by_market)
            if match:
                matches.append(match)

        logger.info(f"Matched {len(matches)} markets out of {len(target_markets)} target markets")
        return matches

    def _find_best_match(
        self,
        target_market: Dict,
        sharp_by_market: Dict[tuple, List[Dict]]
    ) -> Optional[Dict]:
        """
        Find the best matching sharp market for a target market.
        Sharp books are tried in SHARP_PRIORITY order — the first book with an
        acceptable match wins, so a Pinnacle line beats a FanDuel line.
        """
        market_key = target_market.get('market_key', '')
        target_player = target_market.get('player', '')
        target_selection = target_market.get('selection', '')
        target_line = target_market.get('line')

        # Include any sharp bookmakers not in the priority list, after it
        seen = set(SHARP_PRIORITY)
        extra_books = sorted({bk for (mk, bk) in sharp_by_market if mk == market_key and bk not in seen})

        for book in SHARP_PRIORITY + extra_books:
            candidates = sharp_by_market.get((market_key, book), [])
            if not candidates:
                continue

            # Filter candidates by selection type (Over/Under)
            if target_selection:
                candidates = [
                    c for c in candidates
                    if c.get('selection', '').lower() == target_selection.lower()
                ]

            best_match = None
            best_score = 0

            for candidate in candidates:
                # Same event required — team/player names alone can collide
                # across different games (teams play multiple times a week).
                # Event names come from the API's event object, so exact
                # equality is safe across bookmakers. commence_time must match
                # too: doubleheaders/series share the same event name.
                if candidate.get('event') != target_market.get('event'):
                    continue
                if (candidate.get('commence_time') and target_market.get('commence_time')
                        and candidate.get('commence_time') != target_market.get('commence_time')):
                    continue

                sharp_player = candidate.get('player', '')
                sharp_line = candidate.get('line')

                name_score = fuzz.ratio(
                    target_player.lower(),
                    sharp_player.lower()
                )

                if name_score < self.similarity_threshold:
                    continue

                # Check line tolerance if both have lines
                if target_line is not None and sharp_line is not None:
                    line_diff = abs(target_line - sharp_line)
                    if line_diff > self.line_tolerance:
                        continue

                if name_score > best_score:
                    best_score = name_score
                    best_match = candidate

            if best_match:
                return {
                    'target': target_market,
                    'sharp': best_match,
                    'match_score': best_score
                }

        return None

    def _best_match_in(self, target_market: Dict, candidates: List[Dict]) -> Optional[Dict]:
        """Return the best candidate (by name score) that clears all filters, or None."""
        target_player = target_market.get('player', '')
        target_selection = target_market.get('selection', '')
        target_line = target_market.get('line')

        best_match = None
        best_score = 0
        for candidate in candidates:
            if candidate.get('event') != target_market.get('event'):
                continue
            # Doubleheaders/series share event names — times must match too
            if (candidate.get('commence_time') and target_market.get('commence_time')
                    and candidate.get('commence_time') != target_market.get('commence_time')):
                continue
            if target_selection and candidate.get('selection', '').lower() != target_selection.lower():
                continue

            name_score = fuzz.ratio(target_player.lower(), candidate.get('player', '').lower())
            if name_score < self.similarity_threshold:
                continue

            sharp_line = candidate.get('line')
            if target_line is not None and sharp_line is not None:
                if abs(target_line - sharp_line) > self.line_tolerance:
                    continue

            if name_score > best_score:
                best_score = name_score
                best_match = candidate

        return best_match

    def match_markets_multi(
        self,
        target_markets: List[Dict],
        sharp_markets: List[Dict]
    ) -> List[Dict]:
        """
        Like match_markets, but attaches EVERY sharp book that carries the line
        (one best match per book) instead of only the single sharpest one.
        OddsJam-style: one target line vs all sharp books side by side.

        Returns:
        {
            'target': {...},
            'sharps': {'pinnacle': {...}, 'draftkings': {...}, 'fanduel': {...}},
            'match_score': 95.5
        }
        """
        # Group sharp markets by (market_key, bookmaker)
        sharp_by_market = {}
        for market in sharp_markets:
            key = (market.get('market_key', ''), market.get('bookmaker', ''))
            sharp_by_market.setdefault(key, []).append(market)

        # Which books exist for each market_key, priority order first
        matches = []
        for target_market in target_markets:
            market_key = target_market.get('market_key', '')
            seen = set(SHARP_PRIORITY)
            extra = sorted({bk for (mk, bk) in sharp_by_market if mk == market_key and bk not in seen})

            sharps = {}
            best_overall = 0
            for book in SHARP_PRIORITY + extra:
                candidates = sharp_by_market.get((market_key, book), [])
                if not candidates:
                    continue
                match = self._best_match_in(target_market, candidates)
                if match:
                    sharps[book] = match
                    score = fuzz.ratio(
                        target_market.get('player', '').lower(),
                        match.get('player', '').lower()
                    )
                    best_overall = max(best_overall, score)

            if sharps:
                matches.append({
                    'target': target_market,
                    'sharps': sharps,
                    'match_score': best_overall
                })

        logger.info(f"Multi-matched {len(matches)} of {len(target_markets)} target markets across sharp books")
        return matches

    def find_two_sided_pairs(self, markets: List[Dict]) -> List[Dict]:
        """
        Find Over/Under pairs for the same market to enable vig removal.
        Pairs are grouped per bookmaker so a Pinnacle 'over' is never combined
        with a DraftKings 'under' — mixing books would corrupt the vig math.

        Returns:
            List of paired markets:
            {
                'bookmaker': 'pinnacle',
                'market_key': 'player_points',
                'player': 'LeBron James',
                'line': 25.5,
                'over': {...},
                'under': {...}
            }
        """
        pairs = []

        # Group by (bookmaker, player, market_key, line)
        market_groups = {}
        for market in markets:
            key = (
                market.get('bookmaker', ''),
                market.get('player', ''),
                market.get('market_key', ''),
                market.get('line')
            )
            market_groups.setdefault(key, {})
            selection = market.get('selection', '').lower()
            market_groups[key][selection] = market

        # Find complete pairs
        for key, selections in market_groups.items():
            if 'over' in selections and 'under' in selections:
                bookmaker, player, market_key, line = key
                pairs.append({
                    'bookmaker': bookmaker,
                    'market_key': market_key,
                    'player': player,
                    'line': line,
                    'over': selections['over'],
                    'under': selections['under']
                })

        logger.info(f"Found {len(pairs)} two-sided pairs across sharp books")
        return pairs


def match_markets(
    target_markets: List[Dict],
    sharp_markets: List[Dict],
    similarity_threshold: float = 80.0,
    line_tolerance: float = 0.5
) -> List[Dict]:
    """Convenience function to match markets."""
    matcher = MarketMatcher(similarity_threshold, line_tolerance)
    return matcher.match_markets(target_markets, sharp_markets)
