# Deploy to Render.com - Quick Guide

## Step 1: Push Code to GitHub

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Ready for deployment"

# Create GitHub repo at github.com/new, then:
git remote add origin https://github.com/YOUR_USERNAME/FliffJam.git
git branch -M main
git push -u origin main
```

## Step 2: Deploy on Render

1. Go to **[render.com](https://render.com)** and sign up (free)
2. Click **"New +"** → **"Web Service"**
3. Click **"Connect GitHub"** and authorize
4. Select your **FliffJam** repository
5. Render auto-detects settings from `render.yaml`
6. Click **"Create Web Service"**

## Step 3: Add API Keys

In Render dashboard:
1. Go to your service
2. Click **"Environment"** in left sidebar
3. Click **"Add Environment Variable"**
4. Add: `ODDS_API_KEY` = `your_api_key_here`
5. Click **"Save Changes"**

The app will automatically redeploy!

## Your Live URL
`https://fliff-ev-bot.onrender.com` (or whatever name you chose)

## Free Tier Notes
- App sleeps after 15 min of inactivity (first request takes ~30 sec to wake)
- 750 hours/month free (plenty for personal use)
- Upgrade to $7/mo for always-on + custom domain

## Updating Your App
Just push to GitHub:
```bash
git add .
git commit -m "Update"
git push
```
Render auto-deploys in ~2 minutes!
