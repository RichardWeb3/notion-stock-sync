# notion_price_update.py — configurable tickers + Change % + multi-source + robust
import os, datetime, time, random, requests, csv, io, re, sys
from dotenv import load_dotenv
from yfinance.exceptions import YFRateLimitError
import yfinance as yf

load_dotenv()
TOKEN = (os.getenv("NOTION_TOKEN") or "").strip()
DBID  = (os.getenv("NOTION_DATABASE_ID") or "").strip()
ALPHA = (os.getenv("ALPHA_VANTAGE_KEY") or "").strip()

if not TOKEN:
    sys.exit("NOTION_TOKEN missing. Check your env/Secrets.")
if not re.fullmatch(r"[0-9a-fA-F-]{32,36}", DBID or ""):
    sys.exit("NOTION_DATABASE_ID missing/invalid.")

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_db_meta():
    r = requests.get(f"https://api.notion.com/v1/databases/{DBID}", headers=H)
    r.raise_for_status()
    return r.json()

META = get_db_meta()
TITLE_PROP = next(k for k,v in META["properties"].items() if v["type"] == "title")
HAS_CHANGE_COL = ("Change %" in META["properties"] and META["properties"]["Change %"]["type"] == "number")

# ---------- helpers ----------
def is_crypto_usd_pair(ticker: str) -> bool:
    t = ticker.upper()
    return "-" in t and t.endswith("-USD")

# Coinbase for crypto
def price_from_coinbase(ticker: str, timeout=10) -> float:
    url = f"https://api.coinbase.com/v2/prices/{ticker.upper()}/spot"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    return float(r.json()["data"]["amount"])

# Stooq for US stocks/ETFs
def stooq_symbol(ticker: str) -> str:
    return f"{ticker.lower()}.us"

def price_from_stooq(ticker: str, timeout=10) -> float:
    url = f"https://stooq.com/q/d/l/?s={stooq_symbol(ticker)}&i=d"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    text = r.text.strip()
    if len(text.splitlines()) < 2:
        raise ValueError("No data from Stooq")
    close = None
    for row in csv.DictReader(io.StringIO(text)):
        if row.get("Close"):
            close = row["Close"]
    if close is None:
        raise ValueError("No close in Stooq CSV")
    return float(close)

# Alpha Vantage for equities (optional)
def price_from_alpha_vantage(ticker: str, timeout=15) -> float:
    if not ALPHA:
        raise RuntimeError("ALPHA_VANTAGE_KEY not set")
    url = "https://www.alphavantage.co/query"
    params = {"function": "GLOBAL_QUOTE", "symbol": ticker.upper(), "apikey": ALPHA}
    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    js = r.json()
    price = js.get("Global Quote", {}).get("05. price")
    if not price:
        raise ValueError(f"AlphaVantage equity no data: {js}")
    return float(price)

# Yahoo fallback with backoff
def price_from_yahoo(ticker: str, max_tries=5) -> float:
    wait = 1.0
    last_err = None
    for _ in range(max_tries):
        try:
            hist = yf.Ticker(ticker).history(period="10d")
            close = hist["Close"].dropna()
            if not close.empty:
                return float(round(close.iloc[-1], 4))
            last_err = ValueError("Empty Yahoo history")
        except Exception as e:
            last_err = e
        time.sleep(wait + random.uniform(0, 0.5))
        wait = min(wait * 2, 16)
    raise last_err or RuntimeError("Yahoo failed")

def get_last_price(ticker: str) -> float:
    if is_crypto_usd_pair(ticker):
        # Crypto: Coinbase -> Yahoo
        try:
            return price_from_coinbase(ticker)
        except Exception:
            return price_from_yahoo(ticker)
    else:
        # Equities/ETFs: Stooq -> Alpha (optional) -> Yahoo
        try:
            return price_from_stooq(ticker)
        except Exception:
            pass
        if ALPHA:
            try:
                return price_from_alpha_vantage(ticker)
            except Exception:
                pass
        return price_from_yahoo(ticker)

# ---------- Notion helpers ----------
def load_tickers():
    try:
        with open("tickers.txt") as f:
            return [x.strip() for x in f if x.strip() and not x.strip().startswith("#")]
    except FileNotFoundError:
        return ["ILMN", "QQQ", "BTC-USD"]

def find_today_page(ticker: str, day: str):
    q = {
        "filter": {
            "and": [
                {"property": TITLE_PROP, "title": {"equals": ticker}},
                {"property": "Date", "date": {"equals": day}}
            ]
        },
        "page_size": 1
    }
    r = requests.post(f"https://api.notion.com/v1/databases/{DBID}/query", headers=H, json=q)
    r.raise_for_status()
    rs = r.json().get("results", [])
    return rs[0]["id"] if rs else None

def last_record_price_in_notion(ticker: str, before_day: str):
    q = {
      "filter": {"and":[
        {"property": TITLE_PROP, "title": {"equals": ticker}},
        {"property": "Date", "date": {"before": before_day}}
      ]},
      "sorts": [{"property":"Date","direction":"descending"}],
      "page_size": 1
    }
    r = requests.post(f"https://api.notion.com/v1/databases/{DBID}/query", headers=H, json=q)
    r.raise_for_status()
    rows = r.json().get("results", [])
    if not rows:
        return None
    return rows[0]["properties"]["Outcome"]["number"]

def upsert_price(ticker: str, price: float, day: str):
    prev = last_record_price_in_notion(ticker, day)
    change = None if prev in (None, 0) else (price/prev - 1.0)

    props = {
        "Date": {"date": {"start": day}},
        TITLE_PROP: {"title": [{"text": {"content": ticker}}]},
        "Action": {"rich_text": [{"text": {"content": "Auto price update"}}]},
        "Outcome": {"number": price}
    }
    if HAS_CHANGE_COL:
        props["Change %"] = {"number": change}

    page_id = find_today_page(ticker, day)
    if page_id:
        r = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=H, json={"properties": props})
        print(f"UPDATE {ticker} ->", r.status_code)
    else:
        r = requests.post("https://api.notion.com/v1/pages", headers=H, json={"parent": {"database_id": DBID}, "properties": props})
        print(f"CREATE {ticker} ->", r.status_code)

if __name__ == "__main__":
    tickers = load_tickers()
    day = datetime.date.today().isoformat()
    for t in tickers:
        try:
            px = get_last_price(t)
            upsert_price(t, px, day)
            time.sleep(0.6 + random.uniform(0, 0.6))
        except Exception as e:
            print(f"Skip {t}: {e}")
