# 🏗️ Myfactory Import Tool

CLI/Web tool to import articles from CSV into Myfactory CRM.

## Features
- CSV parsing with delimiter detection
- Field mapping (saved in `config.json`)
- Secure `.env` secrets
- CLI + Web UI (FastAPI)
- Full logging
- EXE packaging

## Quick Start
```bash
# Setup
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# Copy config
cp config/config.example.json config/config.json
cp config/.env.example config/.env

# Run
python src/main.py --file sample.csv --mapping default --dry-run
python src/main.py --validate-config