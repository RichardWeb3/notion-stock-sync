# notion_price_update.py (robust batch version)
import os, datetime, time, random, requests
from dotenv import load_dotenv
import pandas as pd
import yfinance as yf
from yfinance.exceptions import YFRateLimitError

load_dotenv()
TOKEN = os.getenv("NOTION_TOKEN")
DBID  = os.getenv("NOTION_DATABASE_ID")

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

def batch_last_closes(tickers, max_tries=5):
    """
    批量获取最后一个有效收盘价，带指数退避与随机抖动。
    返回: {ticker: price_float}
    """
    wait = 1.0
    for attempt in range(max_tries):
        try:
            df = yf.download(
                tickers=tickers,
                period="10d",          # 回看 10 天，避免周末/节假日无数据
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True
            )
            prices = {}
            # 处理单/多 ticker 两种表结构
            if isinstance(df.columns, pd.MultiIndex):
                for t in tickers:
                    try:
                        s = df[t]["Close"].dropna()
                        if not s.empty:
                            prices[t] = float(round(s.iloc[-1], 4))
                    except Exception:
                        pass
            else:
                # 单 ticker 情况
                s = df["Close"].dropna()
                if not s.empty:
                    prices[tickers[0]] = float(round(s.iloc[-1], 4))

            # 如果都成功取到，或已经到最后一次尝试，就返回
            if prices or attempt == max_tries - 1:
                return prices

            # 少量缺失：小睡后再尝试一次
            time.sleep(wait + random.uniform(0, 0.5))
            wait *= 2
        except YFRateLimitError:
            # 被限流：退避重试
            time.sleep(wait + random.uniform(0, 0.5))
            wait *= 2
        except Exception:
            # 其他网络异常也退避重试
            time.sleep(wait + random.uniform(0, 0.5))
            wait *= 2
    return {}

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
    # 想跟踪哪些资产就写在这里
    tickers = ["ILMN", "QQQ", "BTC-USD"]

    day = datetime.date.today().isoformat()
    prices = batch_last_closes(tickers)

    if not prices:
        raise SystemExit("Failed to fetch prices (rate-limited or network issue). Try again later.")

    # 逐个写入 Notion（之间稍作间隔，进一步降低限流概率）
    for t in tickers:
        if t in prices:
            upsert_price(t, prices[t], day)
            time.sleep(0.5 + random.uniform(0, 0.5))
        else:
            print(f"Skip {t}: no price fetched.")

