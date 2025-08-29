# notion_price_update.py — multi-source + backoff
import os, datetime, time, random, requests, csv, io
from dotenv import load_dotenv
from yfinance.exceptions import YFRateLimitError
import yfinance as yf

load_dotenv()
TOKEN = os.getenv("NOTION_TOKEN")
DBID  = os.getenv("NOTION_DATABASE_ID")
ALPHA = os.getenv("ALPHA_VANTAGE_KEY")  # 可为空

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

def get_title_prop():
    meta = requests.get(f"https://api.notion.com/v1/databases/{DBID}", headers=H)
    meta.raise_for_status()
    meta = meta.json()
    return next(k for k,v in meta["properties"].items() if v["type"] == "title")

TITLE_PROP = get_title_prop()

# ---------- 数据源 1：Stooq（免 key） ----------
def stooq_symbol(ticker: str) -> str:
    t = ticker.upper()
    if "-" in t:  # crypto, e.g., BTC-USD
        return t.lower()  # 'btc-usd'
    return f"{t.lower()}.us"  # US 股票/ETF：qqq.us / ilmn.us

def price_from_stooq(ticker: str, timeout=10) -> float:
    sym = stooq_symbol(ticker)
    url = f"https://stooq.com/q/d/l/?s={sym}&i=d"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    text = r.text.strip()
    lines = text.splitlines()
    if len(lines) < 2:
        raise ValueError("No data from Stooq")
    # 解析 CSV 最后一行的收盘价
    close = None
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        if row.get("Close"):
            close = row["Close"]
    if close is None:
        raise ValueError("No close in Stooq CSV")
    return float(close)

# ---------- 数据源 2：Alpha Vantage（免费 key） ----------
def price_from_alpha_vantage(ticker: str, timeout=15) -> float:
    if not ALPHA:
        raise RuntimeError("ALPHA_VANTAGE_KEY not set")
    t = ticker.upper()
    if "-" in t:  # crypto
        base, quote = t.split("-", 1)
        url = "https://www.alphavantage.co/query"
        params = {"function": "DIGITAL_CURRENCY_DAILY",
                  "symbol": base, "market": quote, "apikey": ALPHA}
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        js = r.json()
        ts = js.get("Time Series (Digital Currency Daily)") or {}
        if not ts:
            raise ValueError(f"AlphaVantage crypto no data: {js}")
        latest_day = sorted(ts.keys())[-1]
        price = ts[latest_day].get("4b. close (USD)")
        if not price:
            # 部分市场字段为 4a. close (USD)
            price = ts[latest_day].get("4a. close (USD)")
        if not price:
            raise ValueError("AlphaVantage crypto close missing")
        return float(price)
    else:
        url = "https://www.alphavantage.co/query"
        params = {"function": "GLOBAL_QUOTE", "symbol": t, "apikey": ALPHA}
        r = requests.get(url, params=params, timeout=timeout)
        r.raise_for_status()
        js = r.json()
        q = js.get("Global Quote", {})
        price = q.get("05. price")
        if not price:
            raise ValueError(f"AlphaVantage equity no data: {js}")
        return float(price)

# ---------- 数据源 3：Yahoo Finance（带退避） ----------
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
        except YFRateLimitError as e:
            last_err = e
        except Exception as e:
            last_err = e
        time.sleep(wait + random.uniform(0, 0.5))
        wait = min(wait * 2, 16)
    raise last_err or RuntimeError("Yahoo failed")

# ---------- 统一获取价 ----------
def get_last_price(ticker: str) -> float:
    # 按 Stooq -> Alpha -> Yahoo 的顺序
    # 1) Stooq
    try:
        return price_from_stooq(ticker)
    except Exception:
        pass
    # 2) Alpha Vantage
    if ALPHA:
        try:
            return price_from_alpha_vantage(ticker)
        except Exception:
            pass
    # 3) Yahoo
    return price_from_yahoo(ticker)

# ---------- Notion upsert ----------
def find_today_page(ticker: str, day: str):
    q = {
        "filter": {
            "and": [
                {"property": TITLE_PROP, "title": { "equals": ticker }},
                {"property": "Date", "date": { "equals": day }}
            ]
        },
        "page_size": 1
    }
    r = requests.post(f"https://api.notion.com/v1/databases/{DBID}/query", headers=H, json=q)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0]["id"] if results else None

def upsert_price(ticker: str, price: float, day: str):
    props = {
        "Date": {"date": {"start": day}},
        TITLE_PROP: {"title": [{"text": {"content": ticker}}]},
        "Action": {"rich_text": [{"text": {"content": "Auto price update"}}]},
        "Outcome": {"number": price}
    }
    page_id = find_today_page(ticker, day)
    if page_id:
        r = requests.patch(f"https://api.notion.com/v1/pages/{page_id}", headers=H, json={"properties": props})
        print(f"UPDATE {ticker} ->", r.status_code)
    else:
        r = requests.post("https://api.notion.com/v1/pages", headers=H, json={"parent": {"database_id": DBID}, "properties": props})
        print(f"CREATE {ticker} ->", r.status_code)

if __name__ == "__main__":
    # 自由增删
    tickers = ["ILMN", "QQQ", "BTC-USD"]
    day = datetime.date.today().isoformat()

    for t in tickers:
        try:
            px = get_last_price(t)
            upsert_price(t, px, day)
            time.sleep(0.8 + random.uniform(0, 0.7))  # 间隔，进一步稳妥
        except Exception as e:
            print(f"Skip {t}: {e}")
