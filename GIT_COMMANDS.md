# Git Commands to Push to GitHub

## Initial Setup (if repo not initialized)

```bash
cd "C:\Users\Kyle\OneDrive\Desktop\FliffJam"

# Initialize git repository
git init

# Add all files (respects .gitignore)
git add .

# Create first commit
git commit -m "Complete Fliff +EV bot implementation

Features:
- TheOddsAPI integration for Fliff & Pinnacle odds
- Fuzzy market matching with RapidFuzz  
- Vig removal and EV calculation engine
- Beautiful responsive web UI with filtering
- CSV export functionality
- Comprehensive test suite (all passing)
- Full documentation and quick start guide

Tech stack:
- Python 3.11+ / Flask 3.0
- requests, cachetools, rapidfuzz, python-dotenv
- HTML/CSS/JavaScript (vanilla)

API endpoints:
- GET /api/ev - Fetch all opportunities  
- GET /api/export - Download CSV
- GET /api/health - Health check

See README.md for setup instructions."

# Add remote repository (replace with your repo URL if different)
git remote add origin https://github.com/Ravenmaker215/fliff_ai_bot.git

# Push to GitHub
git push -u origin main
```

## If Repo Already Exists

If you already have commits and want to add these changes:

```bash
cd "C:\Users\Kyle\OneDrive\Desktop\FliffJam"

# Check current status
git status

# Add new/modified files
git add .

# Commit with message
git commit -m "Add complete +EV finder implementation with TheOddsAPI"

# Push to GitHub
git push origin main
```

## Verify Before Pushing

```bash
# See what will be committed
git status

# See what changed
git diff

# See commit history
git log --oneline
```

## Important Notes

1. **API Key Protection**: 
   - Your `.env` file with API key is in `.gitignore`
   - It will NOT be pushed to GitHub (secure!)
   - Only `.env.example` is committed (template)

2. **Files That Will Be Committed**:
   - ✅ All Python source code
   - ✅ HTML templates
   - ✅ Tests
   - ✅ Documentation (README, etc.)
   - ✅ requirements.txt
   - ✅ .gitignore
   - ✅ .env.example (no secrets)
   - ❌ .env (your actual API key - protected!)
   - ❌ __pycache__/ directories
   - ❌ Virtual environments

3. **Branch Name**:
   - Default is `main` (recommended)
   - If your repo uses `master`, change commands accordingly

4. **Authentication**:
   - GitHub may prompt for credentials
   - Use Personal Access Token (not password)
   - Or configure SSH keys

## Create GitHub Release (Optional)

Once pushed, you can create a release on GitHub:

1. Go to: https://github.com/Ravenmaker215/fliff_ai_bot
2. Click "Releases" → "Create a new release"
3. Tag: `v1.0.0`
4. Title: `Fliff +EV Finder v1.0`
5. Description: Copy from IMPLEMENTATION_SUMMARY.md
6. Publish release

## Clone on Another Machine

To use this on another computer:

```bash
# Clone the repo
git clone https://github.com/Ravenmaker215/fliff_ai_bot.git
cd fliff_ai_bot

# Copy example env and add your API key
copy .env.example .env
# Edit .env and add your API key

# Install dependencies
python -m pip install -r requirements.txt

# Run the app
python server.py
```

---

**Ready to share your work with the world! 🚀**
