# notion-stock-sync

![License](https://img.shields.io/github/license/bx-labs/notion-stock-sync)
![Stars](https://img.shields.io/github/stars/bx-labs/notion-stock-sync)
![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)

Sync your **stock portfolio** with **Notion** in real-time.

---

## ✨ Features
- ✅ Auto-update market value, cost basis, and gains  
- ✅ Integrates with multiple brokers & APIs  
- ✅ Clean, customizable dashboards in Notion  
- ✅ Formula-ready (PnL, ROI, Market Value)  

---

## 🚀 Quick Start

### 1. Clone repo
```bash
git clone https://github.com/bx-labs/notion-stock-sync.git
cd notion-stock-sync
```

### 2. Setup environment
```bash
python -m venv .venv
source .venv/bin/activate    # Windows 用 .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure `.env`
复制 `.env.example` → `.env`，并填写：
```
NOTION_API_KEY=your_notion_key
NOTION_DATABASE_ID=your_database_id
BROKER_API_KEY=your_broker_key   # 如果需要
```

### 4. Run sync
```bash
python sync.py
```

运行后，脚本会自动拉取股票价格并写入你的 Notion 数据库。

---

## 📝 Notion Setup

在 Notion 建立一个数据库，包含以下列：
- **Symbol** (Title)  
- **Shares** (Number)  
- **Cost Basis** (Number)  
- **Fees** (Number, optional)  
- **Market Value** (Number, 2 decimals, 由脚本更新)  

### 常用公式

**Invested**
```text
if(or(empty(prop("Cost Basis")), empty(prop("Shares"))), 0, prop("Cost Basis") * prop("Shares") + if(empty(prop("Fees")), 0, prop("Fees")))
```

**PnL**
```text
prop("Market Value") - prop("Invested")
```

---

## 📸 Screenshot
<p align="center">
  <img src="docs/screenshots/notion-stock-sync.png" width="700" alt="notion-stock-sync demo"/>
</p>

---

## 📍 Roadmap
- [ ] Broker adapters: Alpaca / IBKR / Robinhood  
- [ ] Scheduler & retry logic  
- [ ] Dashboard templates (Notion + web)  

---

## 🤝 Contributing
欢迎 PR & Issue！  
- Fork 本仓库  
- 新建分支：`git checkout -b feature-xyz`  
- 提交修改后 PR  

---

## 📜 License
MIT License © [bx-labs](https://github.com/bx-labs)

---

# 📊 Project Intro (简洁版)

> ⚡ 用于 **GitHub Pages** / **Product Hunt** / **快速展示**

Sync your **stock portfolio** with **Notion** in real-time.

### Why use this?
- Auto-update **Market Value / Cost Basis / PnL**  
- Works with multiple brokers & APIs  
- Ready-to-use **Notion dashboard**  
- Lightweight, Python-based  

### Quick Start
```bash
git clone https://github.com/bx-labs/notion-stock-sync.git
cd notion-stock-sync
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in your Notion key & database ID
python sync.py
```

### Demo
<p align="center">
  <img src="docs/screenshots/notion-stock-sync.png" width="700" alt="notion-stock-sync demo"/>
</p>

⭐️ From [bx-labs](https://github.com/bx-labs)
