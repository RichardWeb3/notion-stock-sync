# Notion Stock Sync

Automate daily price updates from Yahoo Finance (`yfinance`) into a Notion database, with optional Alpha Vantage fallback and Slack alerting. This repo includes a production-ready GitHub Actions workflow and Notion formulas for portfolio P&L.

> ✅ This README matches the setup you’ve built: *tickers.txt* driven, Asia/Singapore date, single active workflow, environment self-checks, and safe secrets handling.

---

## Contents
- [Features](#features)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Notion Setup](#notion-setup)
- [Local Setup](#local-setup)
- [Environment Variables](#environment-variables)
- [Tickers List](#tickers-list)
- [Run Locally](#run-locally)
- [GitHub Actions (CI) Setup](#github-actions-ci-setup)
- [Workflow YAML (reference)](#workflow-yaml-reference)
- [Notion Formulas](#notion-formulas)
- [SSH over 443 (reliable Git pushes)](#ssh-over-443-reliable-git-pushes)
- [Backfill Historical Data (optional)](#backfill-historical-data-optional)
- [Troubleshooting](#troubleshooting)
- [Maintenance Checklist](#maintenance-checklist)
- [License](#license)

---

## Features
- **Daily price sync** to Notion by *ticker + date* (idempotent upsert).
- **Time-zone aware** dates (Asia/Singapore) to avoid UTC off-by-one.
- **Configurable tickers** via `tickers.txt` (no code change required).
- **Safe secrets** via GitHub Actions Secrets (no `.env` in git).
- **Self-check step** in CI to validate environment before running.
- **yfinance with retry/backoff**, optional Alpha Vantage fallback.
- **Optional Slack alerts** on CI failure or large price changes.
- **Notion formula columns** for Invested, Market Value, Unrealized P&L, and %.

---

## Architecture
```
tickers.txt ──► Python (yfinance) ──► Notion API
                        │                ▲
                        └──── GitHub Actions (cron + manual dispatch)
                                   │
                            Slack (optional on failure)
```
- **Notion**: a database with specific columns (see below).
- **Python**: fetch prices, compute fields, upsert by `(stock/asset, Date)`.
- **GitHub Actions**: scheduled run daily + manual trigger.

---

## Prerequisites
- Python 3.11+ (local dev)
- A Notion **internal integration** with capabilities: *Read content / Update content / Insert content*.
- A Notion **database** shared to that integration (**Share → Invite → your integration → Can edit**).
- GitHub repository (this repo) with Actions enabled.

---

## Notion Setup

### 1) Share Integration to Database
Notion database page → **Share** → **Invite** → select your Integration → **Can edit**.

### 2) Get Database ID
Copy database link (not a single page). The 32/36-char UUID in the URL is your `NOTION_DATABASE_ID`.

### 3) Required Properties (column names are case-sensitive)
Create these columns with exact names:
- `stock/asset` — **Title**
- `Date` — **Date**
- `Outcome` — **Number**
- `Action` — **Rich text**
- `Change %` — **Number** (optional, written by script)

#### Portfolio columns
- `Cost Basis` — **Number**
- `Shares` — **Number**
- `Fees` — **Number** (optional)
- `Invested` — **Formula**
- `Market Value` — **Formula**
- `Unrealized P&L` — **Formula**
- `Unrealized P&L %` — **Formula (format: Percent)**

Formulas are provided [below](#notion-formulas).

---

## Local Setup

```bash
git clone <your-repo-url>
cd notion-stock-sync

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -U pip
pip install requests yfinance python-dotenv
```

Create `.env` from the template:
```bash
cp .env.example .env
# then edit .env to fill values (NOTION_TOKEN, NOTION_DATABASE_ID, ...)
```

> **Never commit `.env`**. `.gitignore` already excludes it.

---

## Environment Variables

Use `.env` locally and **GitHub Secrets** in CI.

`.env.example`:
```bash
NOTION_TOKEN=ntn_xxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# optional
ALPHA_VANTAGE_KEY=AV_xxx
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/xxx
```

---

## Tickers List
Edit `tickers.txt` to control what symbols are synced:
```txt
# equities
ILMN
QQQ
# crypto
BTC-USD
```

---

## Run Locally

Minimal Notion write test (connectivity & mapping):
```bash
python notion_minimal_insert.py
```

Main updater:
```bash
python notion_price_update.py
```

- Uses **Asia/Singapore** date for `Date`.
- Upserts by `(stock/asset, Date)`—re-runs are safe.

---

## GitHub Actions (CI) Setup

1. In GitHub repo: **Settings → Secrets and variables → Actions → New repository secret**. Add:  
   - `NOTION_TOKEN`  
   - `NOTION_DATABASE_ID`  
   - (optional) `ALPHA_VANTAGE_KEY`, `SLACK_WEBHOOK_URL`

2. Ensure you only have **one active workflow** file: `.github/workflows/notion_stock_update.yml`.

3. Runs on schedule (cron) and via **Actions → Run workflow** for manual test.

---

## Workflow YAML (reference)

> Keep just one active workflow (.yml) inside `.github/workflows/`.

```yaml
name: Notion Stock Price Update

on:
  schedule:
    - cron: "7 21 * * *"   # UTC 21:07 ≈ Singapore/Beijing 05:07
  workflow_dispatch:

concurrency:
  group: notion-stock-sync
  cancel-in-progress: false

jobs:
  update:
    runs-on: ubuntu-latest
    env:
      NOTION_TOKEN: ${{ secrets.NOTION_TOKEN }}
      NOTION_DATABASE_ID: ${{ secrets.NOTION_DATABASE_ID }}
      ALPHA_VANTAGE_KEY: ${{ secrets.ALPHA_VANTAGE_KEY }}
      SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with: { python-version: "3.11" }
      - uses: actions/cache@v4
        with:
          path: ~/.cache/pip
          key: ${{ runner.os }}-pip-v1
          restore-keys: ${{ runner.os }}-pip-
      - name: Install deps
        run: |
          python -m pip install --upgrade pip
          pip install requests yfinance python-dotenv
      - name: Check env presence (no secrets printed)
        run: |
          python - << 'PY'
          import os, re
          t=(os.getenv("NOTION_TOKEN") or "").strip()
          d=(os.getenv("NOTION_DATABASE_ID") or "").strip()
          print("NOTION_TOKEN set:", bool(t))
          print("DBID set:", bool(d), "| uuid:", bool(re.fullmatch(r"[0-9a-fA-F-]{36}", d)))
          print("ALPHA_VANTAGE_KEY set:", bool((os.getenv('ALPHA_VANTAGE_KEY') or '').strip()))
          PY
      - name: Run updater
        run: python notion_price_update.py
      - name: Notify on failure (Slack)
        if: ${{ failure() && env.SLACK_WEBHOOK_URL != '' }}
        run: |
          curl -X POST -H 'Content-type: application/json' \
            --data '{"text":"❌ Notion stock update failed for '${{ github.repository }}' (#${{ github.run_number }})"}' \
            "$SLACK_WEBHOOK_URL"
```

---

## Notion Formulas

> Use **exact** property names. Set **Number format** to *Number* (2 decimals) where applicable. For `%`, set *Percent*.

**Invested**
```notion
if(
  or(empty(prop("Cost Basis")), empty(prop("Shares"))),
  0,
  prop("Cost Basis") * prop("Shares") + if(empty(prop("Fees")), 0, prop("Fees"))
)
```

**Market Value**
```notion
if(
  or(empty(prop("Outcome")), empty(prop("Shares"))),
  0,
  prop("Outcome") * prop("Shares")
)
```

**Unrealized P&L**
```notion
prop("Market Value") - prop("Invested")
```

**Unrealized P&L %**  *(set column format to Percent)*
```notion
if(
  prop("Invested") == 0,
  0,
  (prop("Market Value") - prop("Invested")) / prop("Invested")
)
```

> If you already use `Position Size` as shares, replace `prop("Shares")` with `prop("Position Size")` in formulas.

---

## SSH over 443 (reliable Git pushes)

`~/.ssh/config`:
```sshconfig
Host github.com
  HostName ssh.github.com
  Port 443
  User git
  AddKeysToAgent yes
  UseKeychain yes
  IdentityFile ~/.ssh/id_ed25519
```

Then switch remote:
```bash
git remote set-url origin git@github.com:YOUR_USER/notion-stock-sync.git
ssh -T git@github.com  # should say: You've successfully authenticated
```

---

## Backfill Historical Data (optional)

Create `backfill.py` and run once to fill past N days.

```python
import datetime, time, random
from zoneinfo import ZoneInfo
from notion_price_update import load_tickers, upsert_price, last_close

def daterange(days: int):
    tz = ZoneInfo("Asia/Singapore")
    today = datetime.datetime.now(tz).date()
    for i in range(days, 0, -1):
        yield (today - datetime.timedelta(days=i)).isoformat()

tickers = load_tickers()
for day in daterange(90):
    for t in tickers:
        try:
            px = last_close(t)
            upsert_price(t, px, day)
            time.sleep(0.4 + random.random()*0.4)
        except Exception as e:
            print("Skip", t, day, e)
```

Run:
```bash
python backfill.py
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| **403** from Notion | DB not shared to integration | Database → Share → Invite integration (**Can edit**) |
| **400** validation error | Column name mismatch | Ensure Notion property names exactly match |
| **Invalid header value b'***'** | Printed masked secrets in headers | Never print secrets; only print boolean presence |
| **YFRateLimitError** | Yahoo throttling | Retry/backoff; fewer tickers; optional Alpha Vantage fallback |
| **Actions succeeded but wrong date** | UTC date | Use `ZoneInfo("Asia/Singapore")` |
| **Push blocked (secrets)** | `.env` committed | `git rm --cached .env`; add `.gitignore`; push again |
| **HTTPS push timeout** | Network | Use SSH (port 443) as shown above |

---

## Maintenance Checklist
- Only one active workflow under `.github/workflows/`.
- Rotate Notion token quarterly; update GitHub Secrets.
- `tickers.txt` is the single source of truth for symbols.
- Keep self-check step in Actions to catch misconfig early.
- Protect `main` branch; use feature branches + PRs.

---

## License
MIT — do whatever you want, but no warranty. Adjust as needed for your org.
