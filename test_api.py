"""
Quick test script to check TheOddsAPI response
"""
import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('ODDS_API_KEY')
BASE_URL = "https://api.the-odds-api.com/v4"

print(f"Testing with API Key: {API_KEY[:8]}...")

# Test 1: Get available sports
print("\n1. Testing available sports...")
response = requests.get(
    f"{BASE_URL}/sports",
    params={'apiKey': API_KEY}
)
print(f"Status: {response.status_code}")
sports = response.json()
print(f"Found {len(sports)} sports")
for sport in sports[:5]:
    print(f"  - {sport['key']}: {sport['title']}")

# Test 2: Get available bookmakers for NBA
print("\n2. Testing NBA bookmakers...")
response = requests.get(
    f"{BASE_URL}/sports/basketball_nba/odds",
    params={
        'apiKey': API_KEY,
        'regions': 'us',
        'markets': 'h2h'
    }
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Found {len(data)} NBA games")
    if data:
        print("Available bookmakers in first game:")
        for bookie in data[0].get('bookmakers', []):
            print(f"  - {bookie['key']}: {bookie['title']}")
else:
    print(f"Error: {response.text}")

# Test 3: Check if Fliff is available
print("\n3. Checking Fliff availability...")
response = requests.get(
    f"{BASE_URL}/sports/basketball_nba/odds",
    params={
        'apiKey': API_KEY,
        'regions': 'us',
        'bookmakers': 'fliff',
        'markets': 'player_points'
    }
)
print(f"Status: {response.status_code}")
remaining = response.headers.get('x-requests-remaining', 'unknown')
print(f"API requests remaining: {remaining}")

if response.status_code == 200:
    data = response.json()
    print(f"Found {len(data)} games with Fliff odds")
    
    fliff_count = 0
    for game in data:
        for bookie in game.get('bookmakers', []):
            if bookie['key'] == 'fliff':
                fliff_count += 1
                print(f"\nFliff found in: {game['home_team']} vs {game['away_team']}")
                print(f"Markets available: {len(bookie.get('markets', []))}")
                if bookie.get('markets'):
                    print(f"First market: {bookie['markets'][0]['key']}")
                break
    
    print(f"\nTotal games with Fliff: {fliff_count}")
else:
    print(f"Error: {response.text}")

# Test 4: Check Pinnacle
print("\n4. Checking Pinnacle availability...")
response = requests.get(
    f"{BASE_URL}/sports/basketball_nba/odds",
    params={
        'apiKey': API_KEY,
        'regions': 'us',
        'bookmakers': 'pinnacle',
        'markets': 'player_points'
    }
)
print(f"Status: {response.status_code}")
if response.status_code == 200:
    data = response.json()
    print(f"Found {len(data)} games with Pinnacle odds")
else:
    print(f"Error: {response.text}")

print("\n" + "="*50)
print("Test complete!")
