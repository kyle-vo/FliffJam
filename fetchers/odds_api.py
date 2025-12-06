"""
TheOddsAPI fetcher for both Fliff and Pinnacle data.
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

# Cache for 3 hours to avoid burning API requests
CACHE_TTL = int(os.getenv('CACHE_TTL', 10800))  # 3 hours (10800 seconds) default
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
        """Make API request with error handling."""
        url = f"{self.BASE_URL}/{endpoint}"
        params['apiKey'] = self.api_key
        
        try:
            response = self.session.get(url, params=params, timeout=10)
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
        Fetch odds from Fliff and Pinnacle for NBA and NFL.
        Includes moneylines (h2h), spreads, and player props.
        
        Args:
            sports: List of sport keys. Defaults to NBA and NFL.
        
        Returns:
            {
                'fliff': [normalized_markets],
                'pinnacle': [normalized_markets]
            }
        """
        # Check if we have cached data from file
        cached_data = load_cache()
        if cached_data:
            logger.info("📦 Using cached data (avoiding API calls)")
            return cached_data
        
        if sports is None:
            # Only NBA and NFL per user preference
            sports = ['basketball_nba', 'americanfootball_nfl']
        
        fliff_markets = []
        pinnacle_markets = []
        
        # Markets to fetch - h2h and spreads work with regular odds endpoint
        game_markets = ['h2h', 'spreads']
        
        # Player props require event-specific endpoint
        player_markets = {
            'basketball_nba': ['player_points', 'player_rebounds', 'player_assists'],
            'americanfootball_nfl': ['player_pass_tds', 'player_pass_yds', 'player_rush_yds']
        }
        
        for sport in sports:
            # Fetch game markets (h2h, spreads)
            for market in game_markets:
                # Fetch Fliff data
                try:
                    logger.info(f"Fetching Fliff {market} for {sport}...")
                    fliff_events = self.get_odds(
                        sport=sport,
                        regions='us',
                        markets=market,
                        bookmakers='fliff'
                    )
                    
                    if fliff_events:
                        for event in fliff_events:
                            for bookmaker in event.get('bookmakers', []):
                                if bookmaker['key'] == 'fliff':
                                    normalized = self.normalize_market(event, bookmaker)
                                    fliff_markets.extend(normalized)
                        logger.info(f"  ✅ Got {len(fliff_events)} events")
                    else:
                        logger.warning(f"  ⚠️ No Fliff data for {market}")
                        
                except Exception as e:
                    logger.error(f"  ❌ Error fetching Fliff {market}: {e}")
                
                # Fetch Pinnacle data
                try:
                    logger.info(f"Fetching Pinnacle {market} for {sport}...")
                    sharp_events = self.get_odds(
                        sport=sport,
                        regions='us',
                        markets=market,
                        bookmakers='pinnacle'
                    )
                    
                    if not sharp_events:
                        # Fallback to other sharp books
                        logger.warning("  ⚠️ Pinnacle not available, trying alternatives...")
                        for book in ['lowvig', 'betonlineag']:
                            sharp_events = self.get_odds(
                                sport=sport,
                                regions='us',
                                markets=market,
                                bookmakers=book
                            )
                            if sharp_events:
                                logger.info(f"  ✅ Using {book} as sharp book")
                                break
                    
                    if sharp_events:
                        for event in sharp_events:
                            for bookmaker in event.get('bookmakers', []):
                                normalized = self.normalize_market(event, bookmaker)
                                pinnacle_markets.extend(normalized)
                        logger.info(f"  ✅ Got {len(sharp_events)} events")
                    else:
                        logger.warning(f"  ⚠️ No sharp book data for {market}")
                        
                except Exception as e:
                    logger.error(f"  ❌ Error fetching sharp book {market}: {e}")
            
            # Fetch player props (event-specific endpoint)
            if sport in player_markets:
                logger.info(f"Fetching events for {sport} player props...")
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
                    
                    # Limit to first 3 events to save API requests (was 5)
                    for event in upcoming_events[:3]:
                        event_id = event.get('id')
                        event_name = f"{event.get('home_team')} vs {event.get('away_team')}"
                        
                        # Fetch player props for this event
                        markets_str = ','.join(player_markets[sport])
                        
                        # Fetch Fliff player props
                        try:
                            logger.info(f"  Fetching Fliff player props for {event_name}...")
                            fliff_event_data = self.get_event_odds(
                                sport=sport,
                                event_id=event_id,
                                regions='us',
                                markets=markets_str,
                                bookmakers='fliff'
                            )
                            
                            if fliff_event_data and fliff_event_data.get('bookmakers'):
                                for bookmaker in fliff_event_data['bookmakers']:
                                    if bookmaker['key'] == 'fliff':
                                        normalized = self.normalize_market(fliff_event_data, bookmaker)
                                        fliff_markets.extend(normalized)
                                        logger.info(f"    ✅ Got {len(normalized)} player props")
                            
                        except Exception as e:
                            logger.warning(f"    ⚠️ No Fliff player props: {e}")
                        
                        # Fetch Pinnacle player props
                        try:
                            sharp_event_data = self.get_event_odds(
                                sport=sport,
                                event_id=event_id,
                                regions='us',
                                markets=markets_str,
                                bookmakers='pinnacle'
                            )
                            
                            if not sharp_event_data or not sharp_event_data.get('bookmakers'):
                                # Try alternative books
                                for book in ['lowvig', 'betonlineag', 'draftkings']:
                                    sharp_event_data = self.get_event_odds(
                                        sport=sport,
                                        event_id=event_id,
                                        regions='us',
                                        markets=markets_str,
                                        bookmakers=book
                                    )
                                    if sharp_event_data and sharp_event_data.get('bookmakers'):
                                        break
                            
                            if sharp_event_data and sharp_event_data.get('bookmakers'):
                                for bookmaker in sharp_event_data['bookmakers']:
                                    normalized = self.normalize_market(sharp_event_data, bookmaker)
                                    pinnacle_markets.extend(normalized)
                            
                        except Exception as e:
                            logger.warning(f"    ⚠️ No sharp player props: {e}")
                
                except Exception as e:
                    logger.error(f"  ❌ Error fetching events: {e}")
        
        logger.info(f"📊 REAL DATA LOADED - {len(fliff_markets)} Fliff markets, {len(pinnacle_markets)} sharp book markets")
        
        if not fliff_markets:
            logger.warning("No Fliff data found - falling back to demo")
            return self._get_demo_data()
        
        result = {
            'fliff': fliff_markets,
            'pinnacle': pinnacle_markets
        }
        
        # Save to persistent file cache
        save_cache(result)
        
        return result
    
    def _get_demo_data(self) -> Dict[str, List[Dict]]:
        """
        Return demo data with NBA/NFL moneylines, spreads, and player props.
        Demonstrates Fliff vs Pinnacle comparison with realistic +EV opportunities.
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
        
        # Fliff (recreational book) - with strategic +EV opportunities
        fliff_markets = []
        for m in pinnacle_markets:
            fliff_m = m.copy()
            fliff_m['bookmaker'] = 'fliff'
            
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
        
        logger.info("📊 DEMO DATA LOADED - This is sample data to demonstrate the app")
        logger.info("   To use real data: Fliff must be available in TheOddsAPI")
        
        return {
            'fliff': fliff_markets,
            'pinnacle': pinnacle_markets
        }


# Convenience function
def fetch_odds_data() -> Dict[str, List[Dict]]:
    """Fetch odds data from TheOddsAPI."""
    fetcher = OddsAPIFetcher()
    return fetcher.fetch_all_props()
