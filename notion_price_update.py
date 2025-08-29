# notion_price_update.py — stocks via Stooq/Alpha/Yahoo + crypto via Coinbase
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

# -------- 工具：判断是否是加密对（如 BTC-USD / ETH-USD） --------
def is_crypto_usd_pair(ticker: str) -> bool:
    t = ticker.upper()
    return "-" in t and t.endswith("-USD")

# -------- 数据源：Coinbase（加密） --------
def price_from_coinbase(ticker: str, timeout=10) -> float:
    # ticker 形如 BTC-USD / ETH-USD
    url = f"https://api.coinbase.com/v2/prices/{ticker.upper()}/spot"
    r = requests.get(url, timeout=timeout)
    r.raise_for_status()
    js = r.json()
    amount = js["data"]["amount"]
    return float(amount)

# -------- 数据源：Stooq（股票/ETF，无需 key） --------
def stooq_symbol(ticker: str) -> str:
    t = ticker.upper()
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
    reader = csv.DictReader(io.StringIO(text))
    close = None
    for row in reader:
        if row.get("Close"):
            close = row["Close"]
    if close is None:
        raise ValueError("No close in Stooq CSV")
    return float(close)

# -------- 数据源：Alpha Vantage（可选，免费 key） --------
def price_from_alpha_vantage(ticker: str, timeout=15) -> float:
    if not ALPHA:
        raise RuntimeError("ALPHA_VANTAGE_KEY not set")
    t = ticker.upper()
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

# -------- 数据源：Yahoo（兜底，带退避） --------
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

# -------- 统一获取价：加密优先 Coinbase；股票优先 Stooq --------
def get_last_price(ticker: str) -> float:
    t = ticker.upper()
    if is_crypto_usd_pair(t):
        # Crypto 路线：Coinbase → Alpha(无) → Yahoo
        try:
            return price_from_coinbase(t)
        except Exception:
            pass
        if ALPHA:
            try:
                # 若要用 Alpha 拉 crypto，请改用前一版里的 DIGITAL_CURRENCY_DAILY
                # 这里只在极少数情况下作为兜底，因此直接走 Yahoo
                pass
            except Exception:
                pass
        return price_from_yahoo(t)
    else:
        # 股票/ETF 路线：Stooq → Alpha → Yahoo
        try:
            return price_from_stooq(t)
        except Exception:
            pass
        if ALPHA:
            try:
                return price_from_alpha_vantage(t)
            except Exception:
                pass
        return price_from_yahoo(t)

# -------- Notion upsert --------
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
    tickers = ["ILMN", "QQQ", "BTC-USD"]  # 需要可自行增删
    day = datetime.date.today().isoformat()

    for t in tickers:
        try:
            px = get_last_price(t)
            upsert_price(t, px, day)
            time.sleep(0.6 + random.uniform(0, 0.6))  # 轻微错峰
        except Exception as e:
            print(f"Skip {t}: {e}")
