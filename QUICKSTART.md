# 🚀 Quick Start Guide

## Run the App in 3 Steps

### Step 1: Open Terminal
```powershell
cd "C:\Users\Kyle\OneDrive\Desktop\FliffJam"
```

### Step 2: Start Server
```powershell
python server.py
```

You should see:
```
INFO:__main__:Starting server on http://localhost:5000
 * Running on http://127.0.0.1:5000
```

### Step 3: Open Browser
Navigate to: **http://localhost:5000**

Click **"🔄 Refresh Data"** to fetch live odds and calculate EV!

---

## What You'll See

The app will:
1. ✅ Fetch odds from Fliff and Pinnacle via TheOddsAPI
2. ✅ Match equivalent markets using fuzzy logic
3. ✅ Remove vig from two-sided markets
4. ✅ Calculate EV for each opportunity
5. ✅ Display results sorted by EV (highest first)

---

## Features to Try

### Filtering
- ☑️ **Positive EV Only** - Show only profitable bets
- **Min EV %** - Set minimum threshold (e.g., 2% for significant edges)
- **Sport Filter** - Focus on specific markets

### Sorting
Click any column header to sort:
- **EV %** - Find highest value bets
- **Match Score** - See most confident matches
- **Player** - Alphabetical order

### Export
Click **"📥 Export CSV"** to download all data for analysis

---

## Understanding the Results

### Key Columns

| Column | Meaning |
|--------|---------|
| **Player** | Athlete name |
| **Event** | Game/match |
| **Market** | Prop type (points, rebounds, etc.) |
| **Side** | Over or Under |
| **Line** | Threshold value |
| **Fliff Odds** | Odds offered on Fliff |
| **Pinnacle Odds** | Sharp book odds |
| **True Prob** | Actual probability (after vig removal) |
| **EV %** | Expected return per $1 bet |
| **Match Score** | Confidence in match (0-100%) |

### Color Coding

- 🟢 **Light Green**: Positive EV (profitable)
- 🟢 **Dark Green**: High EV (>5% - very profitable)
- ⚪ **White**: Negative EV (don't bet)

---

## Example Interpretation

```
Player: LeBron James
Market: Player Points
Side: Over
Line: 25.5
Fliff Odds: +150
Pinnacle Odds: +120
True Prob: 42%
EV %: +5.0%
Match Score: 98%
```

**This means:**
- If you bet $100 on Fliff, you'd expect to profit $5 on average
- The match is very confident (98% score)
- True probability of LeBron scoring over 25.5 is 42%
- Fliff is offering better odds than the sharp book (edge!)

---

## Troubleshooting

### "No Fliff markets found"
- Fliff may not be available in your region on TheOddsAPI
- Try different sports or check TheOddsAPI dashboard

### "No Pinnacle markets found"  
- Same as above - availability varies by region/time
- Pinnacle may not have props listed yet for upcoming games

### "No matching markets found"
- Both books have data but no overlapping markets
- Try refreshing later when more props are posted

### API Rate Limit
- Free tier: 500 requests/month
- Each refresh uses 4-8 requests
- Check console: "API requests remaining: X"
- Upgrade at https://the-odds-api.com/pricing

---

## Tips for Best Results

1. **Timing**: Refresh when props just get posted (usually morning/afternoon)
2. **Volume**: More games = more opportunities (NBA/NFL best)
3. **Verification**: Always double-check player names and lines before betting
4. **Bankroll**: Use kelly criterion or flat betting (1-2% of bankroll)
5. **Speed**: Odds move fast - act quickly on high EV bets

---

## Need Help?

1. Check console logs for detailed errors
2. Read `README.md` for full documentation
3. Read `IMPLEMENTATION_SUMMARY.md` for technical details
4. Test API key: http://localhost:5000/api/health

---

## Stop the Server

Press `Ctrl + C` in terminal

---

**Happy hunting for +EV bets! 🎯**
