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
```

## Usage
```bash
python src/main.py --file <csv> [--mapping <name>] [--dry-run] [--batch 100]
```

## Project Structure
```
src/               # Core logic
config/            # config.json + .env
logs/              # Import logs
templates/         # Web UI
```

## Build EXE
```bash
pyinstaller --onefile --name myfactory-import src/main.py
```

## Logs
`logs/import_YYYYMMDD_HHMMSS.log`