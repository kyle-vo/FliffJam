"""Check what's actually available in TheOddsAPI"""
import requests

API_KEY = '56c9e4eb59453e5c87b37ac42441b5c3'

# Check all available bookmakers
print("Checking available bookmakers...")
r = requests.get(
    'https://api.the-odds-api.com/v4/sports/basketball_nba/odds',
    params={
        'apiKey': API_KEY,
        'regions': 'us',
        'markets': 'h2h'
    }
)

if r.status_code == 200:
    all_bookies = set()
    for game in r.json():
        for bookie in game.get('bookmakers', []):
            all_bookies.add(bookie['key'])
    
    print(f"\nFound {len(all_bookies)} bookmakers:")
    for b in sorted(all_bookies):
        print(f"  - {b}")
    
    print(f"\nFliff available: {'fliff' in all_bookies}")
    print(f"Pinnacle available: {'pinnacle' in all_bookies}")
else:
    print(f"Error: {r.status_code} - {r.text}")

# Try checking available sports
print("\n" + "="*50)
print("Checking sports list...")
r = requests.get(
    'https://api.the-odds-api.com/v4/sports',
    params={'apiKey': API_KEY}
)

if r.status_code == 200:
    sports = r.json()
    print(f"Found {len(sports)} sports")
    in_season = [s for s in sports if not s.get('has_outrights')]
    print(f"In-season sports: {len(in_season)}")
