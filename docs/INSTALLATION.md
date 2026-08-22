# LastEdge Strategy Lab — Installation Guide

> **Module:** `LastEdge Strategy Lab`  
> **Requirements:** Python 3.10+ (Cross-Platform: Linux, macOS, Windows)  

---

## 1. Prerequisites

- **Python**: Version 3.10, 3.11, 3.12, or 3.13.
- **Operating System**: Linux (Ubuntu, Debian, Fedora), macOS, or Windows.
- **No MT5 Required**: Strategy Lab operates 100% offline with local CSV/Parquet historical data.

---

## 2. Installation Steps

### Step 1: Clone Repository
```bash
git clone https://github.com/imlast999/lastedge-strategy-lab.git
cd lastedge-strategy-lab
```

### Step 2: Create Virtual Environment
```bash
# Linux / macOS
python3 -m venv venv
source venv/bin/activate

# Windows
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### Step 3: Install Dependencies
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Environment
```bash
cp .env.example .env
```
Default `.env` configuration:
```ini
MT5_OFFLINE_MODE=1
RESEARCH_API_PORT=8082
RESEARCH_DB_PATH=data/research.db
```

### Step 5: Run Quantitative Unit Tests
```bash
python -m pytest tests/
```
All 25 test suites should pass with 100% green.
