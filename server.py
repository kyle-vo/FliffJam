"""
Flask server for Kalshi/PrizePicks EV betting bot.
Provides API endpoints for fetching +EV betting opportunities.
"""
import os
import logging
import csv
from io import StringIO
from flask import Flask, jsonify, render_template, send_file, Response, request
from dotenv import load_dotenv

from fetchers.odds_api import fetch_odds_data, CACHE_FILE
from utils.matching import match_markets, MarketMatcher
from utils.ev_calculator import calculate_ev_from_data, calculate_ev_multi_from_data

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
@app.route('/')
def index():
    """Serve the main UI."""
    return render_template('index.html')


@app.route('/spreads')
def spreads():
    """Serve the spreads view page."""
    return render_template('spreads.html')


@app.route('/slips')
def slips():
    """Serve the slip builder page."""
    return render_template('slips.html')


@app.route('/results')
def results():
    """Serve the tracked-bets results page."""
    return render_template('results.html')


def _get_fetched_at():
    """Cache write time = when data was actually fetched from the API."""
    try:
        import json as _json
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r') as f:
                return _json.load(f).get('timestamp')
    except Exception:
        pass
    return None


def _compute_opportunities():
    """
    Shared pipeline for /api/ev and /api/spreads: fetch, match, de-vig,
    then annotate every opportunity with value, edge, sport and type.
    Live/started games are dropped. Raises ValueError when no data.
    """
    from datetime import datetime, timezone

    odds_data = fetch_odds_data()
    target_markets = odds_data.get('target', [])
    sharp_markets = odds_data.get('sharp', [])

    if not target_markets:
        raise ValueError('No target-book markets found')
    if not sharp_markets:
        raise ValueError('No sharp-book markets found')

    logger.info(f"Fetched {len(target_markets)} target markets and {len(sharp_markets)} sharp markets")

    matched = MarketMatcher().match_markets_multi(target_markets, sharp_markets)
    if not matched:
        raise ValueError('No matching markets found')
    logger.info(f"Matched {len(matched)} markets")

    opportunities = calculate_ev_multi_from_data(target_markets, sharp_markets, matched)

    # Drop live/already-started games
    now = datetime.now(timezone.utc)

    def is_upcoming(opp):
        ct = opp.get('commence_time', '')
        if not ct:
            return True
        try:
            return datetime.fromisoformat(ct.replace('Z', '+00:00')) > now
        except (ValueError, TypeError):
            return True

    opportunities = [opp for opp in opportunities if is_upcoming(opp)]

    # Value: odds difference on a unified scale centered at -100/+100 = 0
    def odds_to_scale(american_odds):
        if american_odds < 0:
            return american_odds + 100  # -105 -> -5
        return american_odds - 100      # +106 -> 6

    for opp in opportunities:
        target_odds = opp.get('target_odds', 0)
        sharp_odds = opp.get('sharp_odds', 0)
        opp['value'] = odds_to_scale(target_odds) - odds_to_scale(sharp_odds)

    # Edge: the number that actually decides money, per book.
    # - Kalshi: fee-adjusted EV%. Kalshi charges ~0.07*P*(1-P) per contract,
    #   worst near coin-flips, so raw EV overstates the edge.
    # - PrizePicks: you're paid flex/power multipliers, not the quoted odds.
    #   Edge = true prob minus the ~54.5%/leg 6-flex breakeven, in prob points.
    PP_FLEX_BREAKEVEN = 0.545
    for opp in opportunities:
        book = (opp.get('target_book') or '').lower()
        true_prob = opp.get('true_probability')
        target_decimal = opp.get('target_decimal')
        if true_prob is None:
            opp['edge'] = None
            continue
        if book == 'kalshi' and target_decimal:
            price = 1.0 / target_decimal            # contract price in $
            fee = 0.07 * price * (1.0 - price)      # Kalshi trading fee
            effective_decimal = 1.0 / (price + fee)
            opp['edge'] = (true_prob * effective_decimal - 1.0) * 100
        elif book == 'prizepicks':
            opp['edge'] = (true_prob - PP_FLEX_BREAKEVEN) * 100
        else:
            opp['edge'] = opp.get('ev_percent')

    # Readable type + sport labels
    type_mapping = {
        'player_points': 'Points',
        'player_rebounds': 'Rebounds',
        'player_assists': 'Assists',
        'player_points_assists': 'Points + Assists',
        'player_points_rebounds': 'Points + Rebounds',
        'player_rebounds_assists': 'Rebounds + Assists',
        'player_points_rebounds_assists': 'Pts + Reb + Ast',
        'spreads': 'Spread',
        'h2h': 'Moneyline',
        'batter_hits': 'Hits',
        'batter_home_runs': 'Home Runs',
        'pitcher_strikeouts': 'Strikeouts',
        'batter_total_bases': 'Total Bases',
        'batter_rbis': 'RBIs'
    }

    sport_display_map = {
        'basketball_nba': 'NBA',
        'basketball_wnba': 'WNBA',
        'baseball_mlb': 'MLB',
        'americanfootball_nfl': 'NFL'
    }

    for opp in opportunities:
        market_key = opp.get('market_key', '')
        event = opp.get('event', '')
        opp['type'] = type_mapping.get(market_key, market_key.replace('_', ' ').title())

        sport_key = opp.get('sport', '')
        if sport_key in sport_display_map:
            opp['sport'] = sport_display_map[sport_key]
        else:
            # Fallback: detect from team names (handles demo data / missing field)
            nfl_teams = ['Chiefs', 'Bills', 'Cowboys', 'Texans', 'Dolphins',
                         'Buccaneers', 'Raiders', 'Broncos', 'Ravens', 'Steelers',
                         'Seahawks', 'Packers', 'Patriots', 'Bengals', 'Browns',
                         'Colts', 'Jaguars', 'Titans', 'Chargers', 'Vikings',
                         'Eagles', 'Washington', '49ers', 'Commanders']
            opp['sport'] = 'NFL' if any(team in event for team in nfl_teams) else 'NBA'

    return opportunities


@app.route('/api/ev')
def get_ev_opportunities():
    """Player props + moneylines with EV/edge (spreads have their own tab)."""
    try:
        opportunities = [o for o in _compute_opportunities() if o.get('market_key') != 'spreads']
        positive_ev = [o for o in opportunities if o['ev'] > 0]
        logger.info(f"Found {len(positive_ev)} positive EV opportunities out of {len(opportunities)} total")
        return jsonify({
            'success': True,
            'count': len(opportunities),
            'positive_ev_count': len(positive_ev),
            'fetched_at': _get_fetched_at(),
            'opportunities': opportunities
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e), 'opportunities': []}), 200
    except Exception as e:
        logger.error(f"Error calculating EV: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'opportunities': []}), 500


@app.route('/api/export')
def export_csv():
    """
    Export EV opportunities as CSV.
    
    Returns:
        CSV file download
    """
    try:
        # Fetch data (same as /api/ev)
        odds_data = fetch_odds_data()
        target_markets = odds_data.get('target', [])
        sharp_markets = odds_data.get('sharp', [])
        
        if not target_markets or not sharp_markets:
            return "No data available", 404
        
        matched = match_markets(target_markets, sharp_markets)
        if not matched:
            return "No matching markets found", 404
        
        opportunities = calculate_ev_from_data(target_markets, sharp_markets, matched)
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'player', 'event', 'market_key', 'selection', 'line',
            'target_book', 'target_odds', 'sharp_book', 'sharp_odds', 'true_probability',
            'ev', 'ev_percent', 'match_score'
        ])

        writer.writeheader()
        for opp in opportunities:
            writer.writerow({
                'player': opp.get('player', ''),
                'event': opp.get('event', ''),
                'market_key': opp.get('market_key', ''),
                'selection': opp.get('selection', ''),
                'line': opp.get('line', ''),
                'target_book': opp.get('target_book', ''),
                'target_odds': opp.get('target_odds', ''),
                'sharp_book': opp.get('sharp_book', ''),
                'sharp_odds': opp.get('sharp_odds', ''),
                'true_probability': f"{opp.get('true_probability', 0):.4f}",
                'ev': f"{opp.get('ev', 0):.4f}",
                'ev_percent': f"{opp.get('ev_percent', 0):.2f}",
                'match_score': f"{opp.get('match_score', 0):.1f}"
            })
        
        # Return CSV as downloadable file
        output.seek(0)
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={'Content-Disposition': 'attachment; filename=ev_opportunities.csv'}
        )
    
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        return str(e), 500


@app.route('/api/spreads')
def get_spreads():
    """Kalshi spread bets vs sharp consensus, same shape as /api/ev."""
    try:
        opportunities = [o for o in _compute_opportunities() if o.get('market_key') == 'spreads']
        positive_ev = [o for o in opportunities if o['ev'] > 0]
        logger.info(f"Spreads: {len(positive_ev)} positive EV of {len(opportunities)} total")
        return jsonify({
            'success': True,
            'count': len(opportunities),
            'positive_ev_count': len(positive_ev),
            'fetched_at': _get_fetched_at(),
            'opportunities': opportunities
        })
    except ValueError as e:
        return jsonify({'success': False, 'error': str(e), 'opportunities': []}), 200
    except Exception as e:
        logger.error(f"Error fetching spreads: {e}", exc_info=True)
        return jsonify({'success': False, 'error': str(e), 'opportunities': []}), 500


@app.route('/api/health')
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'api_key_configured': bool(os.getenv('ODDS_API_KEY'))
    })


if __name__ == '__main__':
    # Check if API key is configured
    if not os.getenv('ODDS_API_KEY'):
        logger.warning("ODDS_API_KEY not found in environment variables!")
        logger.warning("Make sure to set it in your hosting platform")
    
    # Run the Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
