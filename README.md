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


## Development Setup

Run MS SQL Docker instance:
```bash
# Run container
docker run -e 'ACCEPT_EULA=Y' \
  -e 'MSSQL_SA_PASSWORD=YourStrong!Pass123' \
  -p 1433:1433 -d \
  mcr.microsoft.com/azure-sql-edge

# Restart existing
docker start sqlserver

# Check running containers
docker ps

# Stop container
docker stop 9926e9888a49
```

docker run -e 'ACCEPT_EULA=Y' \
  -e 'MSSQL_SA_PASSWORD=YourStrong!Pass123' \
  -p 1433:1433 -d \
  --name=sqlserver \
  --memory=4g \
  --memory-swap=4g \
  mcr.microsoft.com/azure-sql-edge


# Setup configuration
python -m src.main setup

# Import with dry run
python -m src.main import --file data.csv --supplier ACME --dry-run

# Actual import
python -m src.main import --file data.csv --supplier ACME --batch 500

# List mappings
python -m src.main list-mappings --supplier ACME

# Save mapping
python -m src.main save-mapping --supplier ACME --source SKU

# Show history
python -m src.main history --supplier ACME --limit 10

# Test connection
python -m src.main test-connection

# Start API server
python -m src.main api --port 8000

# Export mappings to JSON
python -m src.main export-mappings --supplier ACME --output mappings.json