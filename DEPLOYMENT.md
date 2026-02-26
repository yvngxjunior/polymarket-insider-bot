# Heroku Deployment Guide

**Platform:** Heroku  
**Database:** PostgreSQL (Heroku Postgres add-on)  
**Runtime:** Python 3.11  
**Processes:** 2 dynos (web + bot)

---

## 📋 Prerequisites

1. **Heroku Account** (free tier OK for testing)
2. **Heroku CLI** installed:
   ```bash
   # macOS
   brew install heroku/brew/heroku
   
   # Windows
   # Download from https://devcenter.heroku.com/articles/heroku-cli
   
   # Linux
   curl https://cli-assets.heroku.com/install.sh | sh
   ```

3. **Git** repository cloned locally

---

## 🚀 Deployment Steps

### 1. Login to Heroku

```bash
heroku login
```

---

### 2. Create Heroku App

```bash
# Create app (auto-generate name)
heroku create

# OR create with custom name
heroku create polyinsider-bot

# Output:
# Creating ⬢ polyinsider-bot... done
# https://polyinsider-bot.herokuapp.com/ | https://git.heroku.com/polyinsider-bot.git
```

---

### 3. Add PostgreSQL Add-on

```bash
# Essential plan ($5/month, 10M rows)
heroku addons:create heroku-postgresql:essential-0

# OR Mini plan (free, 10k rows, testing only)
heroku addons:create heroku-postgresql:mini

# Verify DATABASE_URL is set
heroku config:get DATABASE_URL
# → postgres://user:pass@host:5432/dbname
```

---

### 4. Set Environment Variables

```bash
# Copy from your .env file
heroku config:set PRIVATE_KEY="your_polygon_private_key"
heroku config:set PROXY_WALLET="your_proxy_wallet_address"
heroku config:set TELEGRAM_BOT_TOKEN="your_telegram_token"
heroku config:set TELEGRAM_CHAT_ID="your_chat_id"

# Optional: LLM Agent
heroku config:set OPENAI_API_KEY="sk-..."
heroku config:set LLM_ENABLED=true

# Dry run mode (safe for first deploy)
heroku config:set DRY_RUN=true

# Verify all vars
heroku config
```

---

### 5. Deploy

```bash
# Push branch to Heroku
git push heroku feature/phase1-fastapi:main

# OR if on main branch:
git push heroku main

# Watch build logs
heroku logs --tail
```

**Expected output:**
```
remote: -----> Python app detected
remote: -----> Installing python-3.11.8
remote: -----> Installing dependencies with pip
remote:        Collecting fastapi>=0.109.0
remote:        ...
remote: -----> Discovering process types
remote:        Procfile declares types -> web, bot
remote: -----> Compressing...
remote: -----> Launching...
remote:        https://polyinsider-bot.herokuapp.com/ deployed to Heroku
```

---

### 6. Scale Dynos

```bash
# Start web dyno (FastAPI)
heroku ps:scale web=1

# Start bot dyno (main trading loop)
heroku ps:scale bot=1

# Check dyno status
heroku ps
# web.1: up 2026/02/26 17:35:00 +0000 (~ 1m ago)
# bot.1: up 2026/02/26 17:35:05 +0000 (~ 1m ago)
```

---

### 7. Run Database Migrations

```bash
# Migrations are auto-applied on startup via init_db()
# Check logs to confirm:
heroku logs --tail --dyno bot

# Should see:
# [DB] SQLite migration: portfolio_snapshot.daily_reset_date added
# [DB] SQLite migration: tracked_wallets.consecutive_losses added
```

---

### 8. Verify Deployment

```bash
# Health check
curl https://polyinsider-bot.herokuapp.com/health
# {"status":"ok","service":"polyinsider-api","version":"3.1.0"}

# Open Swagger UI
heroku open /docs

# Test API endpoints
curl https://polyinsider-bot.herokuapp.com/api/portfolio
curl https://polyinsider-bot.herokuapp.com/api/positions
```

---

## 📊 Monitoring

### View Logs

```bash
# All logs (web + bot)
heroku logs --tail

# Web dyno only (FastAPI)
heroku logs --tail --dyno web

# Bot dyno only (trading loop)
heroku logs --tail --dyno bot

# Last 500 lines
heroku logs -n 500
```

### Database Console

```bash
# Connect to PostgreSQL
heroku pg:psql

# Run SQL queries
SELECT COUNT(*) FROM copied_trades;
SELECT * FROM portfolio_snapshot;
\q  -- quit
```

### Dyno Status

```bash
# Check if dynos are running
heroku ps

# Restart all dynos
heroku restart

# Restart specific dyno
heroku restart web.1
heroku restart bot.1
```

---

## 💰 Cost Breakdown

| Resource | Plan | Cost/Month |
|----------|------|------------|
| **Web Dyno** | Eco | $5 |
| **Bot Dyno** | Eco | $5 |
| **PostgreSQL** | Essential-0 | $5 |
| **Total** | | **$15/month** |

**Free Tier (Testing):**
- Web dyno: 550 hours/month free (Eco plan)
- PostgreSQL Mini: Free (10k rows limit)
- **Total: $0** (sleeps after 30min inactivity)

---

## 🔧 Troubleshooting

### Error: "Application Error"

```bash
# Check logs for crash reason
heroku logs --tail

# Common issues:
# 1. Missing env vars → heroku config:set KEY=value
# 2. Database not provisioned → heroku addons:create heroku-postgresql:essential-0
# 3. Port binding issue → Procfile uses $PORT (auto-set by Heroku)
```

### Error: "No web processes running"

```bash
# Scale web dyno
heroku ps:scale web=1
```

### Database Connection Error

```bash
# Verify DATABASE_URL
heroku config:get DATABASE_URL

# Restart app to reconnect
heroku restart
```

### Bot Not Trading

```bash
# Check bot dyno logs
heroku logs --tail --dyno bot

# Verify DRY_RUN mode
heroku config:get DRY_RUN
# → If "true", bot won't execute real trades

# Disable dry run (enable real trading)
heroku config:set DRY_RUN=false
heroku restart bot
```

---

## 🔒 Security Best Practices

1. **Never commit `.env` to Git**
   ```bash
   # Add to .gitignore
   echo ".env" >> .gitignore
   ```

2. **Use Heroku config vars for secrets**
   ```bash
   # Good: heroku config:set PRIVATE_KEY=...
   # Bad:  hardcoded in code
   ```

3. **Restrict CORS in production**
   ```python
   # api/main.py
   allow_origins=["https://yourdomain.com"]  # not "*"
   ```

4. **Enable Heroku SSL**
   ```bash
   # Force HTTPS redirects (automatic on Heroku)
   # All *.herokuapp.com domains have SSL by default
   ```

---

## 📈 Scaling

### Horizontal Scaling (More Dynos)

```bash
# Scale to 2 web dynos (load balancing)
heroku ps:scale web=2

# Scale bot to 0 (pause trading)
heroku ps:scale bot=0
```

### Vertical Scaling (Bigger Dynos)

```bash
# Upgrade to Performance-M ($250/month, 2.5GB RAM)
heroku ps:type web=performance-m
heroku ps:type bot=performance-m
```

### Database Scaling

```bash
# Upgrade to Standard-0 ($50/month, 64GB storage)
heroku addons:upgrade heroku-postgresql:standard-0
```

---

## 🧹 Cleanup (Remove App)

```bash
# Delete Heroku app (includes database)
heroku apps:destroy --app polyinsider-bot --confirm polyinsider-bot

# Remove git remote
git remote remove heroku
```

---

## 🔗 Useful Links

- [Heroku Python Docs](https://devcenter.heroku.com/categories/python-support)
- [Heroku Postgres Docs](https://devcenter.heroku.com/categories/postgres-basics)
- [Procfile Reference](https://devcenter.heroku.com/articles/procfile)
- [Heroku Pricing](https://www.heroku.com/pricing)

---

## ✅ Post-Deployment Checklist

- [ ] Health check returns `{"status":"ok"}`
- [ ] Swagger UI accessible at `/docs`
- [ ] Database migrations applied (check logs)
- [ ] Telegram notifications working
- [ ] Bot dyno running (check `heroku ps`)
- [ ] First trade logged in database (if DRY_RUN=false)
- [ ] No errors in `heroku logs --tail`

---

**Ready for Production!** 🚀
