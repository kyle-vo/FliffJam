"""
Flask server for Fliff EV betting bot.
Provides API endpoints for fetching +EV betting opportunities.
"""
import os
import logging
import csv
from io import StringIO
from flask import Flask, jsonify, render_template, send_file, Response, request, session, redirect, url_for
from functools import wraps
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
app.secret_key = os.getenv('SECRET_KEY', os.urandom(24))

# Password protection
APP_PASSWORD = os.getenv('APP_PASSWORD', 'fliff2024')


def require_auth(f):
    """Decorator to require authentication."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('authenticated'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


@app.route('/login', methods=['GET', 'POST'])
def login():
    """Login page."""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == APP_PASSWORD:
            session['authenticated'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='Invalid password')
    return render_template('login.html')


@app.route('/logout')
def logout():
    """Logout and clear session."""
    session.clear()
    return redirect(url_for('login'))


@app.route('/')
@require_auth
def index():
    """Serve the main UI."""
    return render_template('index.html')


@app.route('/spreads')
@require_auth
def spreads():
    """Serve the spreads view page."""
    return render_template('spreads.html')


@app.route('/alternate-spreads')
@require_auth
def alternate_spreads():
    """Serve the alternate spreads view page."""
    return render_template('alternate_spreads.html')


@app.route('/api/ev')
@require_auth
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
        fliff_markets = odds_data.get('fliff', [])
        pinnacle_markets = odds_data.get('pinnacle', [])
        
        if not fliff_markets:
            return jsonify({
                'success': False,
                'error': 'No Fliff markets found',
                'opportunities': []
            }), 200
        
        if not pinnacle_markets:
            return jsonify({
                'success': False,
                'error': 'No Pinnacle markets found',
                'opportunities': []
            }), 200
        
        logger.info(f"Fetched {len(fliff_markets)} Fliff markets and {len(pinnacle_markets)} Pinnacle markets")
        
        # Match markets
        logger.info("Matching markets...")
        matched = match_markets(fliff_markets, pinnacle_markets)
        
        if not matched:
            return jsonify({
                'success': False,
                'error': 'No matching markets found',
                'opportunities': []
            }), 200
        
        logger.info(f"Matched {len(matched)} markets")
        
        # Calculate EV
        logger.info("Calculating EV...")
        opportunities = calculate_ev_from_data(fliff_markets, pinnacle_markets, matched)
        
        # Filter out spreads and alternate_spreads (they have dedicated tabs)
        opportunities = [opp for opp in opportunities if opp.get('market_key') not in ['spreads', 'alternate_spreads']]
        
        # Calculate value (odds difference on unified scale)
        # Scale: -∞, ..., -200, -105, -100/+100 (0), +105, +200, ..., +∞
        for opp in opportunities:
            fliff_odds = opp.get('fliff_odds', 0)
            pinnacle_odds = opp.get('pinnacle_odds', 0)
            
            # Convert American odds to unified scale (center at -100/+100 = 0)
            def odds_to_scale(american_odds):
                if american_odds < 0:
                    return american_odds + 100  # e.g., -105 → -5
                else:
                    return american_odds - 100  # e.g., +106 → 6
            
            fliff_scale = odds_to_scale(fliff_odds)
            pinnacle_scale = odds_to_scale(pinnacle_odds)
            opp['value'] = fliff_scale - pinnacle_scale
        
        # Filter for positive EV only (optional - keeping all for now)
        positive_ev = [opp for opp in opportunities if opp['ev'] > 0]
        
        # Market key to readable type mapping
        type_mapping = {
            'player_points': 'Points',
            'player_rebounds': 'Rebounds',
            'player_assists': 'Assists',
            'spreads': 'Spread',
            'h2h': 'Moneyline'
        }
        
        # Add sport detection and type field for each opportunity
        for opp in opportunities:
            # Determine sport from market_key
            market_key = opp.get('market_key', '')
            event = opp.get('event', '')
            
            # Convert market_key to readable type
            opp['type'] = type_mapping.get(market_key, market_key.replace('_', ' ').title())
            
            # Determine sport - use market_key first (most reliable)
            # NBA-specific markets (all player props are NBA now)
            if 'player_' in market_key:
                opp['sport'] = 'NBA'
            else:
                # For spreads, use team names
                # NFL-only teams (no NBA overlap)
                nfl_only_teams = ['Chiefs', 'Bills', 'Cowboys', 'Texans', 'Dolphins',
                                 'Buccaneers', 'Raiders', 'Broncos', 'Ravens', 'Steelers',
                                 'Seahawks', 'Packers', 'Patriots', 'Bengals', 'Browns',
                                 'Colts', 'Jaguars', 'Titans', 'Chargers', 'Vikings',
                                 'Eagles', 'Washington', '49ers', 'Commanders']
                
                # NBA-only teams (no NFL overlap)
                nba_only_teams = ['Lakers', 'Warriors', 'Celtics', 'Heat', 'Knicks', '76ers',
                                 'Bucks', 'Nets', 'Raptors', 'Clippers', 'Mavericks', 'Nuggets',
                                 'Trail Blazers', 'Blazers', 'Thunder', 'Pelicans',
                                 'Timberwolves', 'Cavaliers', 'Cavs', 'Pistons', 'Wizards']
                
                # Check for unique team names first
                if any(team in event for team in nfl_only_teams):
                    opp['sport'] = 'NFL'
                elif any(team in event for team in nba_only_teams):
                    opp['sport'] = 'NBA'
                else:
                    # Default to NBA for remaining cases
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
        fliff_markets = odds_data.get('fliff', [])
        pinnacle_markets = odds_data.get('pinnacle', [])
        
        if not fliff_markets or not pinnacle_markets:
            return "No data available", 404
        
        matched = match_markets(fliff_markets, pinnacle_markets)
        if not matched:
            return "No matching markets found", 404
        
        opportunities = calculate_ev_from_data(fliff_markets, pinnacle_markets, matched)
        
        # Create CSV in memory
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'player', 'event', 'market_key', 'selection', 'line',
            'fliff_odds', 'pinnacle_odds', 'true_probability',
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
                'fliff_odds': opp.get('fliff_odds', ''),
                'pinnacle_odds': opp.get('pinnacle_odds', ''),
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
            headers={'Content-Disposition': 'attachment; filename=fliff_ev_opportunities.csv'}
        )
    
    except Exception as e:
        logger.error(f"Error exporting CSV: {e}", exc_info=True)
        return str(e), 500


@app.route('/api/spreads')
@require_auth
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
        fliff_markets = odds_data.get('fliff', [])
        pinnacle_markets = odds_data.get('pinnacle', [])
        
        # Group by game and extract spread data
        games = {}
        
        # Process Fliff spreads
        for market in fliff_markets:
            if market.get('market_key') != 'spreads':
                continue
                
            event = market.get('event', '')
            if event not in games:
                games[event] = {
                    'event': event,
                    'commence_time': market.get('commence_time'),
                    'home_team': '',
                    'away_team': '',
                    'fliff_home': None,
                    'fliff_away': None,
                    'pinnacle_home': None,
                    'pinnacle_away': None,
                    'sport': 'NBA'
                }
            
            # Parse home/away teams from event name
            if ' vs ' in event:
                parts = event.split(' vs ')
                games[event]['home_team'] = parts[0].strip()
                games[event]['away_team'] = parts[1].strip()
            
            player = market.get('player', '')
            line = market.get('line')
            odds = market.get('american_odds')
            
            # Determine if this is home or away team
            if player == games[event]['home_team']:
                games[event]['fliff_home'] = {'line': line, 'odds': odds}
            elif player == games[event]['away_team']:
                games[event]['fliff_away'] = {'line': line, 'odds': odds}
        
        # Process Pinnacle spreads
        for market in pinnacle_markets:
            if market.get('market_key') != 'spreads':
                continue
                
            event = market.get('event', '')
            if event not in games:
                games[event] = {
                    'event': event,
                    'commence_time': market.get('commence_time'),
                    'home_team': '',
                    'away_team': '',
                    'fliff_home': None,
                    'fliff_away': None,
                    'pinnacle_home': None,
                    'pinnacle_away': None,
                    'sport': 'NBA'
                }
            
            # Parse home/away teams
            if ' vs ' in event:
                parts = event.split(' vs ')
                games[event]['home_team'] = parts[0].strip()
                games[event]['away_team'] = parts[1].strip()
            
            player = market.get('player', '')
            line = market.get('line')
            odds = market.get('american_odds')
            
            if player == games[event]['home_team']:
                games[event]['pinnacle_home'] = {'line': line, 'odds': odds}
            elif player == games[event]['away_team']:
                games[event]['pinnacle_away'] = {'line': line, 'odds': odds}
        
        # Determine sport for each game
        nfl_teams = ['Chiefs', 'Bills', 'Lions', 'Cowboys', 'Texans', 'Dolphins', 'Jets',
                    'Buccaneers', 'Saints', 'Cardinals', 'Rams', 'Raiders', 'Broncos',
                    'Ravens', 'Steelers', 'Seahawks', 'Falcons', 'Panthers', 'Packers',
                    'Patriots', 'Bengals', 'Browns', 'Colts', 'Jaguars', 'Titans',
                    'Chargers', 'Vikings', 'Eagles', 'Giants', 'Washington', 'Bears',
                    '49ers', 'Commanders']
        
        for event, game in games.items():
            for team in nfl_teams:
                if team in event:
                    game['sport'] = 'NFL'
                    break
        
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
@require_auth
def get_alternate_spreads():
    """API endpoint for fetching alternate spread data with value calculation."""
    try:
        logger.info("Fetching alternate spreads data...")
        
        # Fetch data from TheOddsAPI (will use cache if available)
        odds_data = fetch_odds_data()
        fliff_markets = odds_data.get('fliff', [])
        pinnacle_markets = odds_data.get('pinnacle', [])
        
        if not fliff_markets or not pinnacle_markets:
            logger.warning("No markets found")
            return jsonify([])
        
        logger.info(f"Fetched {len(fliff_markets)} Fliff markets and {len(pinnacle_markets)} Pinnacle markets")
        
        # Match markets
        matched = match_markets(fliff_markets, pinnacle_markets)
        
        if not matched:
            logger.warning("No matching markets found")
            return jsonify([])
        
        # Calculate EV for all markets
        opportunities = calculate_ev_from_data(fliff_markets, pinnacle_markets, matched)
        
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
            fliff_odds = opp.get('fliff_odds')
            pinnacle_odds = opp.get('pinnacle_odds')
            
            if fliff_odds is not None and pinnacle_odds is not None:
                fliff_scale = odds_to_scale(fliff_odds)
                pinnacle_scale = odds_to_scale(pinnacle_odds)
                opp['value'] = fliff_scale - pinnacle_scale
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
