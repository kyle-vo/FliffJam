"""
Tests for the pricing engine: game-market pairing, consensus de-vig,
and the fee/payout-adjusted Edge metric.

Includes the regression test for the doubleheader bug: two games with the
same event name (MLB doubleheaders) must never share a de-vig pair, or a
live game's prices corrupt the upcoming game's probabilities.
"""
import pytest

from utils.ev_calculator import EVCalculator, build_game_pairs, calculate_ev_multi_from_data
from utils.matching import MarketMatcher


def _mk(bookmaker, market_key, player, american, decimal, event='A vs B',
        ct='2026-01-01T00:00:00Z', line=None, selection='', sport='baseball_mlb'):
    return {
        'event': event, 'commence_time': ct, 'bookmaker': bookmaker,
        'market_key': market_key, 'player': player, 'selection': selection,
        'line': line, 'american_odds': american, 'decimal_odds': decimal,
        'sport': sport,
    }


class TestBuildGamePairs:
    """Pairing both sides of two-sided game markets (h2h, spreads)."""

    def test_h2h_pair_both_directions(self):
        markets = [
            _mk('pinnacle', 'h2h', 'A', -110, 1.909),
            _mk('pinnacle', 'h2h', 'B', -110, 1.909),
        ]
        pairs = build_game_pairs(markets)
        key_a = ('h2h', 'pinnacle', 'A vs B', '2026-01-01T00:00:00Z', 'A')
        key_b = ('h2h', 'pinnacle', 'A vs B', '2026-01-01T00:00:00Z', 'B')
        assert pairs[key_a] == (1.909, 1.909)
        assert pairs[key_b] == (1.909, 1.909)

    def test_doubleheader_games_never_share_a_pair(self):
        """REGRESSION: same event name, different start times = separate games.

        Before the fix, a live game's extreme prices (-10000/+1800) paired
        against the upcoming game's normal prices, making a losing bet look
        +20% EV.
        """
        markets = [
            # Live game, nearly settled
            _mk('fanduel', 'h2h', 'A', -10000, 1.01, ct='2026-01-01T00:00:00Z'),
            _mk('fanduel', 'h2h', 'B', 1800, 19.0, ct='2026-01-01T00:00:00Z'),
            # Upcoming game, same matchup name
            _mk('fanduel', 'h2h', 'A', 110, 2.1, ct='2026-01-01T06:00:00Z'),
            _mk('fanduel', 'h2h', 'B', -130, 1.769, ct='2026-01-01T06:00:00Z'),
        ]
        pairs = build_game_pairs(markets)
        upcoming = pairs[('h2h', 'fanduel', 'A vs B', '2026-01-01T06:00:00Z', 'A')]
        assert upcoming == (2.1, 1.769)  # never (1.01, ...) from the live game

    def test_spread_pair_requires_complementary_lines(self):
        good = [
            _mk('pinnacle', 'spreads', 'A', -110, 1.909, line=-3.5),
            _mk('pinnacle', 'spreads', 'B', -110, 1.909, line=3.5),
        ]
        bad = [
            _mk('pinnacle', 'spreads', 'A', -110, 1.909, line=-3.5),
            _mk('pinnacle', 'spreads', 'B', -110, 1.909, line=4.5),  # not -(-3.5)
        ]
        assert len(build_game_pairs(good)) == 2
        assert len(build_game_pairs(bad)) == 0

    def test_one_sided_market_is_not_paired(self):
        markets = [_mk('pinnacle', 'h2h', 'A', -110, 1.909)]
        assert build_game_pairs(markets) == {}

    def test_prop_markets_are_ignored(self):
        markets = [
            _mk('pinnacle', 'player_points', 'LeBron James', -110, 1.909,
                line=25.5, selection='Over'),
            _mk('pinnacle', 'player_points', 'LeBron James', -110, 1.909,
                line=25.5, selection='Under'),
        ]
        assert build_game_pairs(markets) == {}


class TestConsensusDeVig:
    """Weighted multi-book consensus true probability."""

    def _run(self, target, sharp):
        matched = MarketMatcher().match_markets_multi([target], sharp)
        assert matched, 'test setup: target must match sharp markets'
        return calculate_ev_multi_from_data([target], sharp, matched)

    def test_h2h_devig_removes_vig(self):
        """-110/-110 moneyline must de-vig to exactly 50%, not the 52.4% implied."""
        target = _mk('kalshi', 'h2h', 'A', 100, 2.0)
        sharp = [
            _mk('pinnacle', 'h2h', 'A', -110, 1.909),
            _mk('pinnacle', 'h2h', 'B', -110, 1.909),
        ]
        results = self._run(target, sharp)
        assert abs(results[0]['true_probability'] - 0.5) < 1e-9

    def test_consensus_weights_pinnacle_double(self):
        """Consensus = (2*pinnacle + 1*draftkings) / 3."""
        target = _mk('kalshi', 'h2h', 'A', 100, 2.0)
        sharp = [
            # Pinnacle: A at -150/+130 -> de-vigged pA = 0.6/(0.6+0.4348) = 0.5798
            _mk('pinnacle', 'h2h', 'A', -150, 5 / 3),
            _mk('pinnacle', 'h2h', 'B', 130, 2.3),
            # DraftKings: even -> pA = 0.5
            _mk('draftkings', 'h2h', 'A', -110, 1.909),
            _mk('draftkings', 'h2h', 'B', -110, 1.909),
        ]
        results = self._run(target, sharp)
        p_pin = 0.6 / (0.6 + 1 / 2.3)
        expected = (2 * p_pin + 1 * 0.5) / 3
        assert abs(results[0]['true_probability'] - expected) < 1e-9
        assert results[0]['consensus_books'] == 2

    def test_prop_devig_uses_over_under_pair(self):
        """Prop Over at -120 vs Under +100 de-vigs to 54.55% for the Over."""
        target = _mk('prizepicks', 'player_points', 'LeBron James', -137, 1.73,
                     line=25.5, selection='Over', sport='basketball_nba')
        sharp = [
            _mk('pinnacle', 'player_points', 'LeBron James', -120, 1.833,
                line=25.5, selection='Over', sport='basketball_nba'),
            _mk('pinnacle', 'player_points', 'LeBron James', 100, 2.0,
                line=25.5, selection='Under', sport='basketball_nba'),
        ]
        results = self._run(target, sharp)
        over_imp, under_imp = 1 / 1.833, 1 / 2.0
        expected = over_imp / (over_imp + under_imp)
        assert abs(results[0]['true_probability'] - expected) < 1e-9

    def test_fallback_to_implied_when_no_pair(self):
        """With only one side available, fall back to the implied probability."""
        target = _mk('kalshi', 'h2h', 'A', 100, 2.0)
        sharp = [_mk('pinnacle', 'h2h', 'A', -110, 1.909)]
        results = self._run(target, sharp)
        assert abs(results[0]['true_probability'] - 1 / 1.909) < 1e-9
        assert results[0]['consensus_books'] == 0


class TestEdgeMetric:
    """Fee/payout-adjusted Edge computed by the server pipeline."""

    def _opportunities(self, monkeypatch, target, sharp):
        import server
        monkeypatch.setattr(server, 'fetch_odds_data',
                            lambda: {'target': target, 'sharp': sharp})
        return server._compute_opportunities()

    FUTURE = '2030-01-01T00:00:00Z'

    def test_non_prizepicks_targets_are_dropped(self, monkeypatch):
        """The product is PrizePicks-only; other target books never surface."""
        target = [_mk('kalshi', 'h2h', 'A', 100, 2.0, ct=self.FUTURE)]
        sharp = [
            _mk('pinnacle', 'h2h', 'A', -120, 1.833, ct=self.FUTURE),
            _mk('pinnacle', 'h2h', 'B', 100, 2.0, ct=self.FUTURE),
        ]
        assert self._opportunities(monkeypatch, target, sharp) == []

    def test_prizepicks_edge_is_vs_flex_breakeven(self, monkeypatch):
        target = [_mk('prizepicks', 'player_points', 'LeBron James', -137, 1.73,
                      ct=self.FUTURE, line=25.5, selection='Over', sport='basketball_nba')]
        sharp = [
            _mk('pinnacle', 'player_points', 'LeBron James', -130, 1.769,
                ct=self.FUTURE, line=25.5, selection='Over', sport='basketball_nba'),
            _mk('pinnacle', 'player_points', 'LeBron James', 105, 2.05,
                ct=self.FUTURE, line=25.5, selection='Under', sport='basketball_nba'),
        ]
        opps = self._opportunities(monkeypatch, target, sharp)
        opp = opps[0]
        assert abs(opp['edge'] - (opp['true_probability'] - 0.545) * 100) < 1e-9

    def test_live_games_are_dropped(self, monkeypatch):
        past = '2020-01-01T00:00:00Z'

        def prop(book, ct, event, sel):
            return _mk(book, 'player_points', 'LeBron James', -137 if book == 'prizepicks' else -110,
                       1.73 if book == 'prizepicks' else 1.909,
                       ct=ct, event=event, line=25.5, selection=sel, sport='basketball_nba')

        target = [
            prop('prizepicks', past, 'A vs B', 'Over'),
            prop('prizepicks', self.FUTURE, 'C vs D', 'Over'),
        ]
        sharp = [
            prop('pinnacle', past, 'A vs B', 'Over'),
            prop('pinnacle', past, 'A vs B', 'Under'),
            prop('pinnacle', self.FUTURE, 'C vs D', 'Over'),
            prop('pinnacle', self.FUTURE, 'C vs D', 'Under'),
        ]
        opps = self._opportunities(monkeypatch, target, sharp)
        assert len(opps) == 1
        assert opps[0]['event'] == 'C vs D'


class TestMatchingTimeGuard:
    """Matching must never pair markets from different games sharing a name."""

    def test_multi_match_respects_commence_time(self):
        target = _mk('kalshi', 'h2h', 'A', 100, 2.0, ct='2026-01-01T06:00:00Z')
        sharp = [
            # Same event name, DIFFERENT game (live doubleheader opener)
            _mk('pinnacle', 'h2h', 'A', -10000, 1.01, ct='2026-01-01T00:00:00Z'),
        ]
        matched = MarketMatcher().match_markets_multi([target], sharp)
        assert matched == []

    def test_multi_match_same_time_matches(self):
        target = _mk('kalshi', 'h2h', 'A', 100, 2.0)
        sharp = [_mk('pinnacle', 'h2h', 'A', -110, 1.909)]
        matched = MarketMatcher().match_markets_multi([target], sharp)
        assert len(matched) == 1
        assert 'pinnacle' in matched[0]['sharps']
