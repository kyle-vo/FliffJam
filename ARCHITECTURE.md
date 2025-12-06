# Fliff +EV Bot Architecture

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         USER BROWSER                             │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │                    Web UI (index.html)                      │ │
│  │  • Interactive table with sorting & filtering               │ │
│  │  • Real-time stats dashboard                                │ │
│  │  • CSV export button                                        │ │
│  │  • Beautiful gradient design                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↕ HTTP                              │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                      FLASK WEB SERVER                            │
│                         (server.py)                              │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Endpoints:                                                 │ │
│  │  • GET /                → Serve UI                          │ │
│  │  • GET /api/ev          → Calculate EV opportunities        │ │
│  │  • GET /api/export      → Download CSV                      │ │
│  │  • GET /api/health      → Health check                      │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              ↕                                   │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │   Fetchers      │  │   Matching      │  │  EV Calculator  │ │
│  │  odds_api.py    │  │  matching.py    │  │ev_calculator.py │ │
│  │                 │  │                 │  │                 │ │
│  │ • Fetch odds    │  │ • Fuzzy match   │  │ • Remove vig    │ │
│  │ • Normalize     │  │ • Find pairs    │  │ • Calc true prob│ │
│  │ • Cache (5min)  │  │ • Score matches │  │ • Calculate EV  │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
                                ↓
┌─────────────────────────────────────────────────────────────────┐
│                        TheOddsAPI                                │
│                   (api.the-odds-api.com)                         │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Returns odds from multiple bookmakers:                    │ │
│  │  • Fliff (our betting platform)                            │ │
│  │  • Pinnacle (sharp book for true odds)                     │ │
│  │                                                             │ │
│  │  Supports:                                                  │ │
│  │  • NBA, NFL, MLB, NHL                                       │ │
│  │  • 20+ player prop markets                                 │ │
│  │  • Real-time odds updates                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## Data Flow Sequence

```
1. User clicks "Refresh Data"
   ↓
2. Browser → GET /api/ev → Flask Server
   ↓
3. Flask → odds_api.py
   │
   ├─→ Check cache (5min TTL)
   │   └─→ If cached, return immediately
   │
   └─→ If not cached:
       ├─→ Call TheOddsAPI for basketball_nba (Fliff + Pinnacle)
       ├─→ Call TheOddsAPI for americanfootball_nfl
       ├─→ Call TheOddsAPI for baseball_mlb
       └─→ Call TheOddsAPI for icehockey_nhl
   ↓
4. odds_api.py normalizes data:
   {
     player: "LeBron James",
     market: "player_points", 
     selection: "Over",
     line: 25.5,
     odds: -110,
     decimal: 1.909
   }
   ↓
5. Flask → matching.py
   │
   ├─→ Group markets by type
   ├─→ For each Fliff market:
   │   └─→ Find best Pinnacle match using:
   │       • Fuzzy player name (80% similarity)
   │       • Same market type
   │       • Same selection (Over/Under)
   │       • Line within 0.5 tolerance
   ├─→ Return matched pairs
   │
   └─→ Find two-sided pairs (Over + Under)
       └─→ For vig removal
   ↓
6. Flask → ev_calculator.py
   │
   ├─→ For each matched pair:
   │   │
   │   ├─→ Get corresponding Pinnacle Over/Under pair
   │   │   └─→ Calculate implied probabilities:
   │   │       • Over implied = 1 / over_decimal
   │   │       • Under implied = 1 / under_decimal
   │   │       • Total = over_implied + under_implied
   │   │       • Vig = total - 1.0
   │   │
   │   ├─→ Remove vig (multiplicative method):
   │   │   • True over prob = over_implied / total
   │   │   • True under prob = under_implied / total
   │   │
   │   └─→ Calculate EV:
   │       • EV = (fliff_decimal × true_prob) - 1.0
   │       • EV% = EV × 100
   │
   └─→ Sort by EV descending
   ↓
7. Flask → JSON Response:
   {
     success: true,
     count: 42,
     positive_ev_count: 15,
     opportunities: [...]
   }
   ↓
8. Browser receives JSON
   ↓
9. JavaScript renders table:
   ├─→ Color code rows (green = +EV)
   ├─→ Update stats
   ├─→ Enable sorting/filtering
   └─→ Display to user
```

## Component Responsibilities

### fetchers/odds_api.py
**Purpose**: Fetch and normalize odds data  
**Key Functions**:
- `get_odds(sport, bookmakers, markets)` - Fetch from API
- `normalize_market(event, bookmaker)` - Convert to standard format
- `fetch_all_props(sports)` - Get all props for multiple sports
- `_make_request(endpoint, params)` - HTTP client with error handling

**Caching**: Uses `cachetools.TTLCache` (5 min default)

### utils/matching.py
**Purpose**: Match markets between bookmakers  
**Key Functions**:
- `match_markets(fliff, pinnacle)` - Find best matches
- `_find_best_match(fliff_market, pinnacle_candidates)` - Fuzzy matching
- `find_two_sided_pairs(markets)` - Find Over/Under pairs

**Algorithm**: RapidFuzz string matching + exact checks (market type, selection, line)

### utils/ev_calculator.py
**Purpose**: Calculate expected value  
**Key Functions**:
- `remove_vig_multiplicative(over, under)` - Remove bookmaker margin
- `calculate_ev(odds, true_prob)` - Compute EV
- `calculate_ev_with_pairs(matched, pairs)` - Full pipeline

**Math**: Multiplicative vig removal, standard EV formula

### server.py
**Purpose**: Web server and API  
**Endpoints**:
- `/` - Serve HTML UI
- `/api/ev` - Return opportunities as JSON
- `/api/export` - Download CSV
- `/api/health` - System status

**Framework**: Flask 3.0 with JSON responses

### templates/index.html
**Purpose**: User interface  
**Features**:
- Responsive table with sorting
- Filters (positive EV, min EV, sport)
- Stats dashboard
- CSV export link
- Auto-refresh capability

**Tech**: Vanilla JavaScript (no dependencies)

## Caching Strategy

```
┌─────────────────────────────────────────────┐
│         TTLCache (5 minute TTL)             │
├─────────────────────────────────────────────┤
│ Key: "odds_basketball_nba_fliff_pinnacle"   │
│ Value: [list of normalized markets]         │
│ Expires: 5 minutes after fetch              │
├─────────────────────────────────────────────┤
│ Benefits:                                    │
│ • Reduces API calls (500/month limit)       │
│ • Faster response times                     │
│ • Consistent data during timeframe          │
└─────────────────────────────────────────────┘
```

## Error Handling Flow

```
API Request
    ↓
Try: fetch from TheOddsAPI
    ↓
    ├─→ Success → normalize → cache → return
    │
    └─→ Failure (timeout, 429, 500, etc.)
        ↓
        Log error
        ↓
        Return empty list (not crash)
        ↓
        UI shows friendly message
```

## Performance Characteristics

| Operation | Time | API Calls |
|-----------|------|-----------|
| First load (cold cache) | 3-5s | 4-8 |
| Refresh (warm cache) | <100ms | 0 |
| Match 100 markets | ~50ms | 0 |
| Calculate 100 EVs | ~20ms | 0 |
| Export CSV | ~100ms | 0 |

## Scalability Considerations

**Current Design**:
- Single-threaded Flask (development)
- In-memory cache (lost on restart)
- Synchronous API calls

**For Production**:
- Use Gunicorn/uWSGI (multi-worker)
- Redis for shared caching
- Background jobs for API fetching (Celery)
- WebSocket for real-time updates
- Database for historical tracking

## Security Model

```
┌─────────────────────────────────────────┐
│         Environment Variables           │
│  (.env - NOT in git)                    │
│  • ODDS_API_KEY                         │
│  • FLASK_SECRET_KEY                     │
└─────────────────────────────────────────┘
              ↓ Server reads
┌─────────────────────────────────────────┐
│          Flask Backend                  │
│  • Validates API key                    │
│  • Never sends key to client            │
│  • Logs requests                        │
└─────────────────────────────────────────┘
              ↓ HTTP (API responses)
┌─────────────────────────────────────────┐
│         Browser (Client)                │
│  • No secrets exposed                   │
│  • Public endpoints only                │
│  • CORS handled by Flask               │
└─────────────────────────────────────────┘
```

---

**This architecture balances simplicity with functionality for a local-first application.**
