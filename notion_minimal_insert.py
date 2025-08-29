import os, datetime, requests
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("NOTION_TOKEN")
DBID  = os.getenv("NOTION_DATABASE_ID")

H = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28"
}

# 1) 读取数据库元数据，找到 Title 属性名（可能叫 Name/股票/Stock 等）
meta = requests.get(f"https://api.notion.com/v1/databases/{DBID}", headers=H).json()
title_prop = next(k for k,v in meta["properties"].items() if v["type"] == "title")

# 2) 写入一条记录
payload = {
  "parent": {"database_id": DBID},
  "properties": {
    "Date": {"date": {"start": datetime.date.today().isoformat()}},
    title_prop: {"title": [{"text": {"content": "ILMN"}}]},
    "Action": {"rich_text": [{"text": {"content": "Manual insert test"}}]},
    "Outcome": {"number": 123.45}
  }
}

resp = requests.post("https://api.notion.com/v1/pages", headers=H, json=payload)
print(resp.status_code, resp.text)

