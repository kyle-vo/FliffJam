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

from fetchers.odds_api import fetch_odds_data
from utils.matching import match_markets
from utils.ev_calculator import calculate_ev_from_data

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


@app.route('/alternate-spreads')
def alternate_spreads():
    """Serve the alternate spreads view page."""
    return render_template('alternate_spreads.html')


@app.route('/api/ev')
def get_ev_opportunities():
    """
    Fetch and calculate EV opportunities.
    
    Returns:
        JSON response with list of betting opportunities sorted by EV descending
        {
            "success": true,
            "count": 42,
            "positive_ev_count": 15,
            "opportunities": [...]
        }
    """
    try:
        logger.info("Fetching odds data...")
        
        # Fetch data from TheOddsAPI
        odds_data = fetch_odds_data()
        target_markets = odds_data.get('target', [])
        sharp_markets = odds_data.get('sharp', [])
        
        if not target_markets:
            return jsonify({
                'success': False,
                'error': 'No target-book markets found',
                'opportunities': []
            }), 200
        
        if not sharp_markets:
            return jsonify({
                'success': False,
                'error': 'No sharp-book markets found',
                'opportunities': []
            }), 200
        
        logger.info(f"Fetched {len(target_markets)} target markets and {len(sharp_markets)} sharp markets")
        
        # Match markets
        logger.info("Matching markets...")
        matched = match_markets(target_markets, sharp_markets)
        
        if not matched:
            return jsonify({
                'success': False,
                'error': 'No matching markets found',
                'opportunities': []
            }), 200
        
        logger.info(f"Matched {len(matched)} markets")
        
        # Calculate EV
        logger.info("Calculating EV...")
        opportunities = calculate_ev_from_data(target_markets, sharp_markets, matched)
        
        # Filter out spreads and alternate_spreads (they have dedicated tabs)
        opportunities = [opp for opp in opportunities if opp.get('market_key') not in ['spreads', 'alternate_spreads']]
        
        # Calculate value (odds difference on unified scale)
        # Scale: -∞, ..., -200, -105, -100/+100 (0), +105, +200, ..., +∞
        for opp in opportunities:
            target_odds = opp.get('target_odds', 0)
            sharp_odds = opp.get('sharp_odds', 0)
            
            # Convert American odds to unified scale (center at -100/+100 = 0)
            def odds_to_scale(american_odds):
                if american_odds < 0:
                    return american_odds + 100  # e.g., -105 → -5
                else:
                    return american_odds - 100  # e.g., +106 → 6
            
            target_scale = odds_to_scale(target_odds)
            sharp_scale = odds_to_scale(sharp_odds)
            opp['value'] = target_scale - sharp_scale
        
        # Filter for positive EV only (optional - keeping all for now)
        positive_ev = [opp for opp in opportunities if opp['ev'] > 0]
        
        # Market key to readable type mapping
        type_mapping = {
            'player_points': 'Points',
            'player_rebounds': 'Rebounds',
            'player_assists': 'Assists',
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

        # Add sport and type fields for each opportunity
        for opp in opportunities:
            market_key = opp.get('market_key', '')
            event = opp.get('event', '')

            opp['type'] = type_mapping.get(market_key, market_key.replace('_', ' ').title())

            # Use sport field stamped during fetch if available
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
                if any(team in event for team in nfl_teams):
                    opp['sport'] = 'NFL'
                else:
                    opp['sport'] = 'NBA'
        
        logger.info(f"Found {len(positive_ev)} positive EV opportunities out of {len(opportunities)} total")
        
        return jsonify({
            'success': True,
            'count': len(opportunities),
            'positive_ev_count': len(positive_ev),
            'opportunities': opportunities
        })
    
    except Exception as e:
        logger.error(f"Error calculating EV: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'opportunities': []
        }), 500


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
    """
    Fetch and format spread data for spreads view.
    
    Returns:
        JSON response with list of games with spread data
    """
    try:
        logger.info("Fetching spreads data...")
        
        # Fetch data from TheOddsAPI
        odds_data = fetch_odds_data()
        target_markets = odds_data.get('target', [])
        sharp_markets = odds_data.get('sharp', [])
        
        # Group by game and extract spread data
        games = {}
        
        sport_display_map = {
            'basketball_nba': 'NBA',
            'basketball_wnba': 'WNBA',
            'baseball_mlb': 'MLB',
            'americanfootball_nfl': 'NFL'
        }

        def resolve_sport(market):
            sport_key = market.get('sport', '')
            return sport_display_map.get(sport_key, 'NBA')

        # Process target-book spreads
        for market in target_markets:
            if market.get('market_key') != 'spreads':
                continue

            event = market.get('event', '')
            if event not in games:
                games[event] = {
                    'event': event,
                    'commence_time': market.get('commence_time'),
                    'home_team': '',
                    'away_team': '',
                    'target_home': None,
                    'target_away': None,
                    'sharp_home': None,
                    'sharp_away': None,
                    'sport': resolve_sport(market)
                }

            # Parse home/away teams from event name
            if ' vs ' in event:
                parts = event.split(' vs ')
                games[event]['home_team'] = parts[0].strip()
                games[event]['away_team'] = parts[1].strip()

            player = market.get('player', '')
            line = market.get('line')
            odds = market.get('american_odds')
            book = market.get('bookmaker', '')

            # Determine if this is home or away team (first target book wins)
            if player == games[event]['home_team'] and games[event]['target_home'] is None:
                games[event]['target_home'] = {'line': line, 'odds': odds, 'book': book}
            elif player == games[event]['away_team'] and games[event]['target_away'] is None:
                games[event]['target_away'] = {'line': line, 'odds': odds, 'book': book}

        # Process sharp-book spreads — iterate in priority order (Pinnacle
        # first) and never overwrite, so the sharpest available book wins
        sharp_priority = {'pinnacle': 0, 'draftkings': 1, 'fanduel': 2}
        prioritized_sharp = sorted(
            sharp_markets,
            key=lambda m: sharp_priority.get(m.get('bookmaker', ''), 99)
        )
        for market in prioritized_sharp:
            if market.get('market_key') != 'spreads':
                continue

            event = market.get('event', '')
            if event not in games:
                games[event] = {
                    'event': event,
                    'commence_time': market.get('commence_time'),
                    'home_team': '',
                    'away_team': '',
                    'target_home': None,
                    'target_away': None,
                    'sharp_home': None,
                    'sharp_away': None,
                    'sport': resolve_sport(market)
                }

            # Parse home/away teams
            if ' vs ' in event:
                parts = event.split(' vs ')
                games[event]['home_team'] = parts[0].strip()
                games[event]['away_team'] = parts[1].strip()

            player = market.get('player', '')
            line = market.get('line')
            odds = market.get('american_odds')

            book = market.get('bookmaker', '')
            if player == games[event]['home_team'] and games[event]['sharp_home'] is None:
                games[event]['sharp_home'] = {'line': line, 'odds': odds, 'book': book}
            elif player == games[event]['away_team'] and games[event]['sharp_away'] is None:
                games[event]['sharp_away'] = {'line': line, 'odds': odds, 'book': book}
        
        games_list = list(games.values())
        
        logger.info(f"Found {len(games_list)} games with spreads")
        
        return jsonify({
            'success': True,
            'count': len(games_list),
            'games': games_list
        })
        
    except Exception as e:
        logger.error(f"Error fetching spreads: {e}", exc_info=True)
        return jsonify({
            'success': False,
            'error': str(e),
            'games': []
        }), 500


@app.route('/api/alternate-spreads')
def get_alternate_spreads():
    """API endpoint for fetching alternate spread data with value calculation."""
    try:
        logger.info("Fetching alternate spreads data...")
        
        # Fetch data from TheOddsAPI (will use cache if available)
        odds_data = fetch_odds_data()
        target_markets = odds_data.get('target', [])
        sharp_markets = odds_data.get('sharp', [])
        
        if not target_markets or not sharp_markets:
            logger.warning("No markets found")
            return jsonify([])
        
        logger.info(f"Fetched {len(target_markets)} target markets and {len(sharp_markets)} sharp markets")
        
        # Match markets
        matched = match_markets(target_markets, sharp_markets)
        
        if not matched:
            logger.warning("No matching markets found")
            return jsonify([])
        
        # Calculate EV for all markets
        opportunities = calculate_ev_from_data(target_markets, sharp_markets, matched)
        
        # Filter for alternate_spreads only
        alt_spreads_data = [opp for opp in opportunities if opp.get('market_key') == 'alternate_spreads']
        
        # Add value calculation for each opportunity
        def odds_to_scale(american_odds):
            """Convert American odds to unified scale centered at -100/+100 = 0."""
            if american_odds < 0:
                return american_odds + 100  # -105 → -5
            else:
                return american_odds - 100  # +106 → 6
        
        for opp in alt_spreads_data:
            target_odds = opp.get('target_odds')
            sharp_odds = opp.get('sharp_odds')
            
            if target_odds is not None and sharp_odds is not None:
                target_scale = odds_to_scale(target_odds)
                sharp_scale = odds_to_scale(sharp_odds)
                opp['value'] = target_scale - sharp_scale
            else:
                opp['value'] = None
        
        logger.info(f"Returning {len(alt_spreads_data)} alternate spread opportunities")
        return jsonify(alt_spreads_data)
    except Exception as e:
        logger.error(f"Error in /api/alternate-spreads: {str(e)}")
        return jsonify({'error': str(e)}), 500


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
