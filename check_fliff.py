"""
Check what bookmakers and markets are actually available from TheOddsAPI
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('ODDS_API_KEY')
BASE_URL = "https://api.the-odds-api.com/v4"

def check_bookmakers():
    """Check all available bookmakers"""
    print("=" * 60)
    print("CHECKING AVAILABLE BOOKMAKERS")
    print("=" * 60)
    
    for sport in ['basketball_nba', 'americanfootball_nfl']:
        print(f"\n🏀 Sport: {sport}")
        try:
            response = requests.get(
                f"{BASE_URL}/sports/{sport}/odds",
                params={
                    'apiKey': API_KEY,
                    'regions': 'us',
                    'markets': 'h2h',
                    'oddsFormat': 'american'
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data and len(data) > 0:
                    bookmakers = set()
                    for event in data[:3]:  # Check first 3 events
                        for book in event.get('bookmakers', []):
                            bookmakers.add(book['key'])
                    
                    print(f"   Available bookmakers ({len(bookmakers)}): {sorted(bookmakers)}")
                    
                    # Check if Fliff exists
                    if 'fliff' in bookmakers:
                        print("   ✅ FLIFF IS AVAILABLE!")
                    else:
                        print("   ❌ Fliff not available")
                else:
                    print("   No events found")
            else:
                print(f"   Error: {response.status_code} - {response.text[:200]}")
                
        except Exception as e:
            print(f"   Error: {e}")

def check_fliff_directly():
    """Try to fetch Fliff data directly"""
    print("\n" + "=" * 60)
    print("TRYING TO FETCH FLIFF DIRECTLY")
    print("=" * 60)
    
    for sport in ['basketball_nba', 'americanfootball_nfl']:
        print(f"\n🏀 Sport: {sport}")
        
        # Try h2h market
        try:
            response = requests.get(
                f"{BASE_URL}/sports/{sport}/odds",
                params={
                    'apiKey': API_KEY,
                    'regions': 'us',
                    'markets': 'h2h',
                    'bookmakers': 'fliff',
                    'oddsFormat': 'american'
                },
                timeout=10
            )
            
            print(f"   H2H Market: Status {response.status_code}")
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Success! {len(data)} events found")
                if data and len(data) > 0:
                    print(f"   Sample event: {data[0].get('home_team')} vs {data[0].get('away_team')}")
                    if data[0].get('bookmakers'):
                        print(f"   Bookmakers in event: {[b['key'] for b in data[0]['bookmakers']]}")
            else:
                print(f"   ❌ Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # Try player props
        markets = ['player_points', 'player_rebounds', 'player_assists', 'player_pass_tds', 'player_pass_yds']
        for market in markets:
            try:
                response = requests.get(
                    f"{BASE_URL}/sports/{sport}/odds",
                    params={
                        'apiKey': API_KEY,
                        'regions': 'us',
                        'markets': market,
                        'bookmakers': 'fliff',
                        'oddsFormat': 'american'
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data and len(data) > 0:
                        print(f"   ✅ {market}: {len(data)} events")
                        break
            except:
                pass

if __name__ == '__main__':
    check_bookmakers()
    check_fliff_directly()
    
    print("\n" + "=" * 60)
    print("CONCLUSION")
    print("=" * 60)
    print("Check the output above to see if Fliff data is available.")
    print("If Fliff is not in the available bookmakers list, it means:")
    print("  1. Your API plan doesn't include Fliff")
    print("  2. Fliff is not available in your region")
    print("  3. TheOddsAPI doesn't have Fliff integrated")
