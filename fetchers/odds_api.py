"""
TheOddsAPI fetcher: target books (where you bet) vs sharp books (the reference).
Fetches player props, normalizes the data, and provides caching.
"""
import os
import requests
import logging
import json
import time
from pathlib import Path
from typing import Dict, List, Optional
from dotenv import load_dotenv
from datetime import datetime, timezone

load_dotenv()

logger = logging.getLogger(__name__)

# Cache for 30 minutes to avoid burning API requests
CACHE_TTL = int(os.getenv('CACHE_TTL', 1800))  # 30 minutes (1800 seconds) default
CACHE_FILE = Path('cache_data.json')

# Multiple API keys for rotation - load from environment variable
# Set in .env as: ODDS_API_KEYS=key1,key2,key3
api_keys_env = os.getenv('ODDS_API_KEYS', '')
if api_keys_env:
    API_KEYS = [key.strip() for key in api_keys_env.split(',')]
else:
    # Fallback to single key for backwards compatibility
    API_KEYS = [os.getenv('ODDS_API_KEY', '')]

current_key_index = 0

# Books you actually bet on (kalshi = exchange, prizepicks = DFS) vs the sharp
# books whose de-vigged lines act as "true" probability. Priority order of
# SHARP_BOOKMAKERS matters: matching prefers the first book that has the line.
TARGET_BOOKMAKERS = [b.strip() for b in os.getenv('TARGET_BOOKMAKERS', 'prizepicks').split(',') if b.strip()]
SHARP_BOOKMAKERS = [b.strip() for b in os.getenv('SHARP_BOOKMAKERS', 'pinnacle,draftkings,fanduel').split(',') if b.strip()]
ALL_BOOKMAKERS = TARGET_BOOKMAKERS + SHARP_BOOKMAKERS


def load_cache() -> Dict:
    """Load cache from file."""
    try:
        if CACHE_FILE.exists():
            with open(CACHE_FILE, 'r') as f:
                cache_data = json.load(f)
                cache_age = time.time() - cache_data.get('timestamp', 0)
                # Check if cache is still valid
                if cache_age < CACHE_TTL:
                    logger.info(f"📦 Using cached data (age: {int(cache_age)}s / {CACHE_TTL}s TTL)")
                    return cache_data.get('data', {})
                else:
                    logger.info(f"⏰ Cache expired (age: {int(cache_age)}s > {CACHE_TTL}s TTL) - fetching fresh data")
        else:
            logger.info("📭 No cache file found - fetching fresh data")
    except Exception as e:
        logger.error(f"Error loading cache: {e}")
    return {}


def save_cache(data: Dict):
    """Save cache to file."""
    try:
        cache_data = {
            'timestamp': time.time(),
            'data': data
        }
        with open(CACHE_FILE, 'w') as f:
            json.dump(cache_data, f)
        logger.info(f"💾 Saved cache to file (TTL: {CACHE_TTL}s)")
    except Exception as e:
        logger.error(f"Error saving cache: {e}")


class OddsAPIFetcher:
    """Fetches odds data from TheOddsAPI for Fliff and Pinnacle."""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, api_key: Optional[str] = None):
        global current_key_index
        
        # Use next key in rotation if no specific key provided
        if api_key is None:
            self.api_key = API_KEYS[current_key_index]
            current_key_index = (current_key_index + 1) % len(API_KEYS)
            logger.info(f"Using API key #{current_key_index + 1} of {len(API_KEYS)}")
        else:
            self.api_key = api_key
        
        if not self.api_key:
            raise ValueError("ODDS_API_KEY not found")
        
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'FliffEVBot/1.0'
        })
    
    def _make_request(self, endpoint: str, params: Dict) -> Optional[Dict]:
        """Make API request with error handling and automatic key rotation on quota exhaustion."""
        global current_key_index
        
        url = f"{self.BASE_URL}/{endpoint}"
        params['apiKey'] = self.api_key
        
        try:
            response = self.session.get(url, params=params, timeout=10)

            # On a quota-exhausted key (402), keep rotating until a key with
            # quota is found — trying just one neighbor fails when several
            # consecutive keys are dead.
            attempts = 0
            while response.status_code == 402 and attempts < len(API_KEYS) - 1:
                logger.warning("⚠️ API key exhausted (402). Rotating...")
                self.api_key = API_KEYS[current_key_index]
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                logger.info(f"🔄 Switched to API key #{current_key_index} of {len(API_KEYS)}")
                params['apiKey'] = self.api_key
                response = self.session.get(url, params=params, timeout=10)
                attempts += 1

            if response.status_code == 402:
                logger.error("❌ All API keys exhausted!")
                return None

            # Call succeeded but drained this key: keep the data, rotate for
            # the next call instead of re-spending a credit now.
            remaining = response.headers.get('x-requests-remaining')
            if remaining is not None and float(remaining) <= 0:
                logger.warning("⚠️ Key drained to 0 remaining — rotating for subsequent calls")
                self.api_key = API_KEYS[current_key_index]
                current_key_index = (current_key_index + 1) % len(API_KEYS)
                params['apiKey'] = self.api_key

            response.raise_for_status()
            
            # Log remaining requests
            remaining = response.headers.get('x-requests-remaining')
            if remaining:
                logger.info(f"API requests remaining: {remaining}")
            
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"API request failed: {e}")
            return None
    
    def get_sports(self) -> List[Dict]:
        """Get list of available sports."""
        data = self._make_request("sports", {})
        return data or []
    
    def get_events(self, sport: str) -> List[Dict]:
        """
        Get list of upcoming events for a sport.
        
        Args:
            sport: Sport key (e.g., 'basketball_nba', 'americanfootball_nfl')
        
        Returns:
            List of events with their IDs
        """
        data = self._make_request(f"sports/{sport}/events", {})
        return data or []
    
    def get_event_odds(self, sport: str, event_id: str, regions: str, markets: str, bookmakers: str = '') -> Optional[Dict]:
        """
        Get odds for a specific event (used for player props).
        
        Args:
            sport: Sport key
            event_id: Event ID from get_events()
            regions: 'us' or 'us,uk,eu'
            markets: e.g., 'player_points,player_rebounds,player_assists'
            bookmakers: e.g., 'fliff,pinnacle'
        
        Returns:
            Event odds data
        """
        params = {
            'regions': regions,
            'markets': markets,
            'oddsFormat': 'american'
        }
        
        if bookmakers:
            params['bookmakers'] = bookmakers
        
        data = self._make_request(f"sports/{sport}/events/{event_id}/odds", params)
        return data
    
    def get_odds(self, sport: str, regions: str, markets: str, bookmakers: str = '') -> List[Dict]:
        """
        Get odds for a specific sport.
        
        Args:
            sport: Sport key (e.g., 'basketball_nba', 'americanfootball_nfl')
            regions: 'us' or 'us,uk,eu'
            markets: e.g., 'player_points,player_rebounds,player_assists'
            bookmakers: e.g., 'fliff,pinnacle' or 'draftkings,fanduel'
        """
        params = {
            'regions': regions,
            'markets': markets,
            'oddsFormat': 'american'
        }
        
        # Only add bookmakers if specified (some bookmakers may not exist)
        if bookmakers:
            params['bookmakers'] = bookmakers
        
        data = self._make_request(f"sports/{sport}/odds", params)
        return data or []
    
    def normalize_market(self, event_data: Dict, bookmaker_data: Dict) -> List[Dict]:
        """
        Normalize odds data into a consistent format.
        
        Returns list of markets with structure:
        {
            'event': 'Team A vs Team B',
            'commence_time': '2025-12-02T19:00:00Z',
            'bookmaker': 'fliff' or 'pinnacle',
            'market_key': 'player_points',
            'player': 'LeBron James',
            'selection': 'Over',
            'line': 25.5,
            'american_odds': -110,
            'decimal_odds': 1.909
        }
        """
        normalized = []
        event_name = event_data.get('home_team', '') + ' vs ' + event_data.get('away_team', '')
        commence_time = event_data.get('commence_time', '')
        bookmaker = bookmaker_data.get('key', '')
        
        for market in bookmaker_data.get('markets', []):
            market_key = market.get('key', '')
            
            for outcome in market.get('outcomes', []):
                name = outcome.get('name', '')
                description = outcome.get('description', '')
                price = outcome.get('price')
                point = outcome.get('point')
                
                # Parse player name and selection
                # For player props, 'description' often contains player name
                # and 'name' contains Over/Under
                player_name = description if description else name
                selection = name if description else ''
                
                # Convert American odds to decimal
                decimal_odds = self._american_to_decimal(price)
                
                normalized.append({
                    'event': event_name,
                    'commence_time': commence_time,
                    'bookmaker': bookmaker,
                    'market_key': market_key,
                    'player': player_name,
                    'selection': selection,
                    'line': point,
                    'american_odds': price,
                    'decimal_odds': decimal_odds
                })
        
        return normalized
    
    @staticmethod
    def _american_to_decimal(american_odds: int) -> float:
        """Convert American odds to decimal odds."""
        if american_odds > 0:
            return (american_odds / 100.0) + 1.0
        else:
            return (100.0 / abs(american_odds)) + 1.0
    
    def fetch_all_props(self, sports: List[str] = None) -> Dict[str, List[Dict]]:
        """
        Fetch odds for target books (kalshi, prizepicks) and sharp books
        (pinnacle, draftkings, fanduel) in a single request per market —
        one combined call costs less API quota than per-book calls.
        Includes moneylines (h2h), spreads, and player props.

        Args:
            sports: List of sport keys. Defaults to NBA and NFL.

        Returns:
            {
                'target': [normalized_markets],   # kalshi + prizepicks
                'sharp': [normalized_markets]     # pinnacle + draftkings + fanduel
            }
        """
        # Check if we have cached data from file
        cached_data = load_cache()
        if cached_data and 'target' in cached_data:
            logger.info("📦 Using cached data (avoiding API calls)")
            return cached_data

        if sports is None:
            sports = ['basketball_nba', 'basketball_wnba', 'baseball_mlb', 'americanfootball_nfl']

        target_markets = []
        sharp_markets = []
        bookmakers_param = ','.join(ALL_BOOKMAKERS)

        def split_by_side(event_data: Dict):
            """Normalize every bookmaker in an event and route to target/sharp."""
            for bookmaker in event_data.get('bookmakers', []):
                key = bookmaker.get('key', '')
                normalized = self.normalize_market(event_data, bookmaker)
                for m in normalized:
                    m['sport'] = event_data.get('_sport', '')
                if key in TARGET_BOOKMAKERS:
                    target_markets.extend(normalized)
                elif key in SHARP_BOOKMAKERS:
                    sharp_markets.extend(normalized)
        
        # PrizePicks-only: player props are the whole product, no game markets
        player_markets = {
            'basketball_nba': ['player_points', 'player_rebounds', 'player_assists'],
            'basketball_wnba': ['player_points', 'player_rebounds', 'player_assists',
                                'player_points_assists', 'player_points_rebounds'],
            'baseball_mlb': ['pitcher_strikeouts', 'batter_total_bases']
        }
        
        for sport in sports:
            # Fetch player props (event-specific endpoint)
            # NFL player props removed to save ~64 API calls
            markets_to_fetch = []
            if sport in player_markets:
                markets_to_fetch = player_markets[sport]
            
            if markets_to_fetch:
                logger.info(f"Fetching events for {sport} event-specific markets...")
                try:
                    events = self.get_events(sport)
                    
                    # Filter out live/commenced games - only get upcoming games
                    now = datetime.now(timezone.utc)
                    upcoming_events = []
                    for evt in events:
                        commence_time_str = evt.get('commence_time', '')
                        if commence_time_str:
                            try:
                                commence_time = datetime.fromisoformat(commence_time_str.replace('Z', '+00:00'))
                                if commence_time > now:
                                    upcoming_events.append(evt)
                            except:
                                pass
                    
                    logger.info(f"  Found {len(upcoming_events)} upcoming events (filtered out {len(events) - len(upcoming_events)} live/past games)")
                    
                    # Fetch all upcoming events — one call per event covers all books
                    for event in upcoming_events:
                        event_id = event.get('id')
                        event_name = f"{event.get('home_team')} vs {event.get('away_team')}"

                        # Build markets string
                        markets_str = ','.join(markets_to_fetch)

                        try:
                            logger.info(f"  Fetching player props for {event_name}...")
                            event_data = self.get_event_odds(
                                sport=sport,
                                event_id=event_id,
                                regions='us',
                                markets=markets_str,
                                bookmakers=bookmakers_param
                            )

                            if event_data and event_data.get('bookmakers'):
                                event_data['_sport'] = sport
                                before = len(target_markets)
                                split_by_side(event_data)
                                logger.info(f"    ✅ Got {len(target_markets) - before} target-book props")

                        except Exception as e:
                            logger.warning(f"    ⚠️ No event data: {e}")

                except Exception as e:
                    logger.error(f"  ❌ Error fetching events: {e}")

        logger.info(f"📊 REAL DATA LOADED - {len(target_markets)} target markets ({'/'.join(TARGET_BOOKMAKERS)}), {len(sharp_markets)} sharp markets ({'/'.join(SHARP_BOOKMAKERS)})")

        if not target_markets:
            logger.warning("No target-book data found - falling back to demo")
            return self._get_demo_data()

        result = {
            'target': target_markets,
            'sharp': sharp_markets
        }

        # Save to persistent file cache
        save_cache(result)

        return result
    
    def _get_demo_data(self) -> Dict[str, List[Dict]]:
        """
        Return demo data with NBA/NFL moneylines, spreads, and player props.
        Demonstrates target-book (kalshi) vs sharp (pinnacle) comparison with
        realistic +EV opportunities.
        """
        # Pinnacle (sharp book) odds - NBA and NFL
        pinnacle_markets = [
            # NBA Moneylines
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'h2h',
                'player': 'Lakers',
                'selection': 'Lakers',
                'line': None,
                'american_odds': -140,
                'decimal_odds': 1.714
            },
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'h2h',
                'player': 'Warriors',
                'selection': 'Warriors',
                'line': None,
                'american_odds': +120,
                'decimal_odds': 2.2
            },
            # NBA Spreads
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'spreads',
                'player': 'Lakers',
                'selection': 'Lakers',
                'line': -3.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'spreads',
                'player': 'Warriors',
                'selection': 'Warriors',
                'line': +3.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            # NBA Player Props
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_points',
                'player': 'LeBron James',
                'selection': 'Over',
                'line': 25.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_points',
                'player': 'LeBron James',
                'selection': 'Under',
                'line': 25.5,
                'american_odds': -110,
                'decimal_odds': 1.909
            },
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_points',
                'player': 'Stephen Curry',
                'selection': 'Over',
                'line': 28.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            },
            {
                'event': 'Lakers vs Warriors',
                'commence_time': '2025-12-03T02:00:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_points',
                'player': 'Stephen Curry',
                'selection': 'Under',
                'line': 28.5,
                'american_odds': -115,
                'decimal_odds': 1.870
            },
            {
                'event': 'Celtics vs Heat',
                'commence_time': '2025-12-03T00:30:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_rebounds',
                'player': 'Jayson Tatum',
                'selection': 'Over',
                'line': 8.5,
                'american_odds': -120,
                'decimal_odds': 1.833
            },
            {
                'event': 'Celtics vs Heat',
                'commence_time': '2025-12-03T00:30:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_rebounds',
                'player': 'Jayson Tatum',
                'selection': 'Under',
                'line': 8.5,
                'american_odds': +100,
                'decimal_odds': 2.0
            },
            {
                'event': 'Celtics vs Heat',
                'commence_time': '2025-12-03T00:30:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_assists',
                'player': 'Jimmy Butler',
                'selection': 'Over',
                'line': 5.5,
                'american_odds': +110,
                'decimal_odds': 2.1
            },
            {
                'event': 'Celtics vs Heat',
                'commence_time': '2025-12-03T00:30:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_assists',
                'player': 'Jimmy Butler',
                'selection': 'Under',
                'line': 5.5,
                'american_odds': -130,
                'decimal_odds': 1.769
            },
            # NFL Moneylines
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'h2h',
                'player': 'Chiefs',
                'selection': 'Chiefs',
                'line': None,
                'american_odds': -180,
                'decimal_odds': 1.556
            },
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'h2h',
                'player': 'Bills',
                'selection': 'Bills',
                'line': None,
                'american_odds': +155,
                'decimal_odds': 2.55
            },
            # NFL Spreads
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'spreads',
                'player': 'Chiefs',
                'selection': 'Chiefs',
                'line': -4.5,
                'american_odds': -108,
                'decimal_odds': 1.926
            },
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'spreads',
                'player': 'Bills',
                'selection': 'Bills',
                'line': +4.5,
                'american_odds': -112,
                'decimal_odds': 1.893
            },
            # NFL Player Props
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_pass_yds',
                'player': 'Patrick Mahomes',
                'selection': 'Over',
                'line': 275.5,
                'american_odds': -115,
                'decimal_odds': 1.870
            },
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_pass_yds',
                'player': 'Patrick Mahomes',
                'selection': 'Under',
                'line': 275.5,
                'american_odds': -105,
                'decimal_odds': 1.952
            },
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_pass_tds',
                'player': 'Josh Allen',
                'selection': 'Over',
                'line': 1.5,
                'american_odds': -125,
                'decimal_odds': 1.8
            },
            {
                'event': 'Chiefs vs Bills',
                'commence_time': '2025-12-08T20:20:00Z',
                'bookmaker': 'pinnacle',
                'market_key': 'player_pass_tds',
                'player': 'Josh Allen',
                'selection': 'Under',
                'line': 1.5,
                'american_odds': +105,
                'decimal_odds': 2.05
            },
        ]
        
        # Target book (soft/recreational side) - with strategic +EV opportunities
        fliff_markets = []
        for m in pinnacle_markets:
            fliff_m = m.copy()
            fliff_m['bookmaker'] = TARGET_BOOKMAKERS[0] if TARGET_BOOKMAKERS else 'kalshi'
            
            # Create realistic +EV situations on select markets
            # NBA Props +EV
            if m['player'] == 'LeBron James' and m['selection'] == 'Over':
                fliff_m['american_odds'] = +105  # vs Pinnacle -110 (+3.5% EV!)
                fliff_m['decimal_odds'] = 2.05
            elif m['player'] == 'Stephen Curry' and m['selection'] == 'Under':
                fliff_m['american_odds'] = -105  # vs Pinnacle -115 (+4.2% EV!)
                fliff_m['decimal_odds'] = 1.952
            elif m['player'] == 'Jayson Tatum' and m['selection'] == 'Over':
                fliff_m['american_odds'] = -110  # vs Pinnacle -120 (+4.2% EV!)
                fliff_m['decimal_odds'] = 1.909
            elif m['player'] == 'Jimmy Butler' and m['selection'] == 'Over':
                fliff_m['american_odds'] = +125  # vs Pinnacle +110 (+5.1% EV!)
                fliff_m['decimal_odds'] = 2.25
            
            # NFL Props +EV
            elif m['player'] == 'Patrick Mahomes' and m['selection'] == 'Over':
                fliff_m['american_odds'] = -105  # vs Pinnacle -115 (+4.3% EV!)
                fliff_m['decimal_odds'] = 1.952
            elif m['player'] == 'Josh Allen' and m['selection'] == 'Over':
                fliff_m['american_odds'] = -115  # vs Pinnacle -125 (+3.9% EV!)
                fliff_m['decimal_odds'] = 1.870
            
            # NBA Moneyline +EV
            elif m['market_key'] == 'h2h' and m['selection'] == 'Warriors':
                fliff_m['american_odds'] = +130  # vs Pinnacle +120 (+2.4% EV!)
                fliff_m['decimal_odds'] = 2.3
            
            # NFL Spread +EV  
            elif m['market_key'] == 'spreads' and m['selection'] == 'Bills':
                fliff_m['american_odds'] = -108  # vs Pinnacle -112 (+1.8% EV!)
                fliff_m['decimal_odds'] = 1.926
            
            else:
                # Make other lines slightly worse (typical soft book)
                if fliff_m['american_odds'] > 0:
                    fliff_m['american_odds'] -= 10
                else:
                    fliff_m['american_odds'] -= 5
                fliff_m['decimal_odds'] = self._american_to_decimal(fliff_m['american_odds'])
            
            fliff_markets.append(fliff_m)
        
        # Add DraftKings and FanDuel variants of every Pinnacle market so the
        # multi-book demo view shows all three sharp columns (each shifted a few
        # cents off Pinnacle, as a soft book would be).
        sharp_markets = list(pinnacle_markets)
        for book, shift in (('draftkings', -6), ('fanduel', -4)):
            for m in pinnacle_markets:
                sm = m.copy()
                sm['bookmaker'] = book
                sm['american_odds'] = m['american_odds'] + (shift if m['american_odds'] > 0 else shift)
                sm['decimal_odds'] = self._american_to_decimal(sm['american_odds'])
                sharp_markets.append(sm)

        logger.info("📊 DEMO DATA LOADED - This is sample data to demonstrate the app")
        logger.info(f"   To use real data: {'/'.join(TARGET_BOOKMAKERS)} must return data from TheOddsAPI")

        return {
            'target': fliff_markets,
            'sharp': sharp_markets
        }


# Convenience function
def fetch_odds_data() -> Dict[str, List[Dict]]:
    """Fetch odds data from TheOddsAPI."""
    fetcher = OddsAPIFetcher()
    return fetcher.fetch_all_props()
