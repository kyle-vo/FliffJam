# 🎯 FliffJam — +EV Finder

A Python Flask application that identifies positive expected value (+EV) betting opportunities by comparing the odds you can bet (**Kalshi**, **PrizePicks**) against sharp bookmakers (**Pinnacle**, **DraftKings**, **FanDuel**) via TheOddsAPI. The app fetches moneyline, spread, and player-prop markets, matches them using fuzzy logic, removes vig from the sharp side, and calculates true probabilities to find profitable betting edges.

**Configurable books** — set `TARGET_BOOKMAKERS` (books you bet on) and `SHARP_BOOKMAKERS` (the reference) in your environment; they default to `kalshi,prizepicks` and `pinnacle,draftkings,fanduel`. When several sharp books carry a line, the sharpest available (Pinnacle first) is used.

## 🌟 Features

- **Automated Data Fetching**: Pulls real-time odds for all configured books in a single API call per market via TheOddsAPI
- **Intelligent Market Matching**: Uses fuzzy string matching to pair equivalent markets across bookmakers
- **Vig Removal**: Removes bookmaker margins from two-sided markets to calculate true probabilities
- **EV Calculation**: Computes expected value for each bet opportunity
- **Beautiful Web UI**: Interactive table with filtering, sorting, and highlighting for positive EV bets
- **CSV Export**: Download all opportunities for further analysis
- **Caching**: Smart caching to minimize API calls and stay within rate limits
- **Comprehensive Testing**: Unit tests for matching and EV calculation logic

## 📋 Prerequisites

- Python 3.8 or higher
- TheOddsAPI key (get one at https://the-odds-api.com/)
- Git (optional, for cloning)

## 🚀 Quick Start

### 1. Clone or Download the Repository

```bash
git clone https://github.com/Ravenmaker215/fliff_ai_bot.git
cd fliff_ai_bot
```

Or download and extract the ZIP file.

### 2. Install Dependencies

```bash
python -m pip install -r requirements.txt
```

### 3. Configure Environment

Copy the example environment file and add your API key:

```bash
copy .env.example .env
```

Edit `.env` and add your TheOddsAPI key:

```env
ODDS_API_KEY=your_api_key_here
```

### 4. Run the Application

```bash
python server.py
```

The server will start at `http://localhost:5000`

### 5. Open in Browser

Navigate to `http://localhost:5000` in your web browser to see the dashboard.

## 📁 Project Structure

```
fliff_ai_bot/
├── fetchers/
│   ├── __init__.py
│   └── odds_api.py          # TheOddsAPI integration
├── utils/
│   ├── __init__.py
│   ├── matching.py          # Fuzzy market matching logic
│   └── ev_calculator.py     # EV calculation and vig removal
├── templates/
│   └── index.html           # Web UI
├── tests/
│   ├── __init__.py
│   ├── test_matching.py
│   └── test_ev_calculator.py
├── .env.example             # Example environment config
├── .env                     # Your actual config (not in git)
├── .gitignore
├── requirements.txt
├── server.py                # Flask application
└── README.md
```

## 🎮 Usage

### Web Interface

1. **Refresh Data**: Click "🔄 Refresh Data" to fetch latest odds
2. **Filter Options**:
   - Toggle "Positive EV Only" to show only profitable bets
   - Set minimum EV percentage threshold
   - Filter by sport/market type
3. **Sort**: Click any column header to sort by that field
4. **Export**: Click "📥 Export CSV" to download all data

### API Endpoints

#### GET `/api/ev`
Fetch all EV opportunities as JSON.

**Response:**
```json
{
  "success": true,
  "count": 42,
  "positive_ev_count": 15,
  "opportunities": [
    {
      "player": "LeBron James",
      "event": "Lakers vs Warriors",
      "market_key": "player_points",
      "selection": "Over",
      "line": 25.5,
      "target_book": "kalshi",
      "target_odds": -110,
      "sharp_book": "pinnacle",
      "sharp_odds": -105,
      "true_probability": 0.52,
      "ev": 0.0087,
      "ev_percent": 0.87,
      "match_score": 95.5
    }
  ]
}
```

#### GET `/api/export`
Download opportunities as CSV file.

#### GET `/api/health`
Health check endpoint.

## 🧮 How It Works

### 1. Data Collection
- Fetches moneyline, spread, and player-prop odds for every configured book via TheOddsAPI
- Supports major sports: NBA, NFL, MLB, NHL
- Covers common prop markets: points, rebounds, assists, touchdowns, etc.

### 2. Market Matching
- Uses `rapidfuzz` for fuzzy string matching on player names
- Configurable similarity threshold (default: 80%)
- Matches markets with same type, selection (Over/Under), and line (with tolerance)

### 3. Vig Removal
- For two-sided markets (Over/Under), calculates implied probabilities
- Removes bookmaker margin using multiplicative method
- Derives true probabilities for each outcome

### 4. EV Calculation
```
EV = (Target_Book_Decimal_Odds × True_Probability) - 1.0
```

Positive EV indicates a profitable betting opportunity.

### 5. Presentation
- Sorts opportunities by EV (highest first)
- Highlights positive EV bets in green
- Shows match quality score for confidence

## 🧪 Running Tests

```bash
python -m pytest tests/ -v
```

Or run individual test files:

```bash
python -m pytest tests/test_ev_calculator.py -v
python -m pytest tests/test_matching.py -v
```

## ⚙️ Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `ODDS_API_KEY` | Yes | - | Your TheOddsAPI key |
| `TARGET_BOOKMAKERS` | No | `kalshi,prizepicks` | Comma-separated books you bet on |
| `SHARP_BOOKMAKERS` | No | `pinnacle,draftkings,fanduel` | Sharp reference books, in priority order |
| `FLASK_ENV` | No | `development` | Flask environment |
| `FLASK_DEBUG` | No | `True` | Enable debug mode |
| `CACHE_TTL` | No | `300` | Cache time-to-live in seconds |
| `PORT` | No | `5000` | Server port |

### Matching Parameters

In `utils/matching.py`, you can adjust:

- `similarity_threshold`: Minimum fuzzy match score (0-100) for player names
- `line_tolerance`: Maximum line difference to consider a match

### Sports Coverage

By default, the app fetches these sports (configurable in `fetchers/odds_api.py`):

- `basketball_nba` - NBA Basketball
- `americanfootball_nfl` - NFL Football  
- `baseball_mlb` - MLB Baseball
- `icehockey_nhl` - NHL Hockey

## 📊 API Rate Limits

TheOddsAPI has rate limits based on your plan. This app implements:

- **Caching**: 5-minute TTL by default to minimize API calls
- **Request Tracking**: Logs remaining API requests in console
- **Efficient Fetching**: Fetches all configured books in a single request per market

## ⚠️ Important Notes

### **Target-book quirks (Kalshi & PrizePicks)**

The two target books behave differently from a traditional sportsbook, which affects how their "EV" should be read:

- **PrizePicks** is a DFS app: standard picks are offered at fixed default odds rather than a true per-pick price, so its EV really measures *line value* versus the sharp consensus. Its demon/goblin variants come through TheOddsAPI as `_alternate` markets.
- **Kalshi** is a low-liquidity prediction exchange trading mostly on game winners (moneylines). A displayed edge may reflect a thin or stale quote that has moved by the time you act — verify before betting.

If a target book returns no data (season/region/plan dependent), the app falls back to demo data so the matching, vig-removal, and EV logic can still be demonstrated. The core logic works with any bookmaker set — change `TARGET_BOOKMAKERS` / `SHARP_BOOKMAKERS` to compare other books.

### Legal & Ethical Considerations

- **Know Your Jurisdiction**: Sports betting laws vary by location. Ensure you're legally permitted to place sports bets in your area.
- **Responsible Gambling**: This tool identifies mathematical edges but doesn't guarantee profits. Never bet more than you can afford to lose.
- **Terms of Service**: Respect each book's terms of service. This app uses public APIs and should not be used for unauthorized activities.

### Technical Limitations

- **Match Accuracy**: Fuzzy matching isn't perfect. Always verify player names and lines before placing bets.
- **Market Availability**: Not all props may be available on both platforms simultaneously.
- **Odds Movement**: Odds change frequently. The displayed odds may have moved by the time you place a bet.
- **Sample Size**: EV calculations assume accurate true probabilities. Small edges may not be statistically significant.

## 🤝 Contributing

Contributions are welcome! Areas for improvement:

- Additional bookmaker integrations
- More sophisticated vig removal methods
- Machine learning for better line predictions
- Mobile-responsive UI enhancements
- Real-time odds updates via WebSockets
- Bet tracking and portfolio management

## 📝 License

This project is open source and available under the MIT License.

## 🙏 Acknowledgments

- TheOddsAPI for providing comprehensive odds data
- Flask framework for the web server
- RapidFuzz for efficient fuzzy matching
- The sports betting analytics community for EV calculation methodologies

## 📞 Support

For issues, questions, or suggestions:

1. Check existing GitHub issues
2. Create a new issue with detailed description
3. Include error logs and configuration (without API keys!)

## 🔮 Roadmap

- [ ] Support for more bookmakers (DraftKings, FanDuel, BetMGM)
- [ ] Historical tracking of EV opportunities
- [ ] Bet slip recommendations based on bankroll management
- [ ] Discord/Telegram notifications for high-EV bets
- [ ] Mobile app version
- [ ] Live odds monitoring dashboard

---

**Happy betting! Remember: The house always has an edge, but with the right tools and discipline, you can find yours. 🎯**
