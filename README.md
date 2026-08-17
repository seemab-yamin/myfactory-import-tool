## 🏗️ Myfactory Import Tool

### 📋 Project Overview

A desktop application (Windows EXE) for importing articles from CSV files into Myfactory CRM, supporting both command-line and web-based UI interfaces.

---

## 🎯 Features

- [ ] CSV file parsing with configurable delimiters
- [ ] Field mapping to Myfactory article master
- [ ] Configuration management (central config file)
- [ ] Secure credential storage (`.env` file)
- [ ] Dual interface: CLI + Web UI (FastAPI)
- [ ] Full logging of import process
- [ ] Windows EXE packaging (PyInstaller)

---

## 📁 Project Structure

```
myfactory-import/
├── src/
│   ├── __init__.py
│   ├── main.py                 # Entry point (CLI)
│   ├── web_ui.py               # FastAPI web interface
│   ├── importer.py             # Core import logic
│   ├── mapper.py               # Field mapping logic
│   ├── config_manager.py       # Config file handler
│   ├── logger.py               # Logging setup
│   └── models.py               # Data models (Pydantic)
├── templates/
│   └── index.html              # Web UI template
├── static/
│   └── style.css               # Web UI styles
├── config/
│   ├── config.json             # Main configuration (mappings, paths)
│   └── .env                    # Secrets (DB credentials, API keys)
├── logs/                       # Import logs
├── requirements.txt
├── pyproject.toml
├── setup.py                    # PyInstaller configuration
├── README.md
└── .gitignore
```

---

## 🚀 Setup Instructions

### Prerequisites

- Python 3.10+
- Microsoft SQL Server access
- Windows VMware environment

### Installation

```bash
# 1. Clone/Setup project
cd myfactory-import

# 2. Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows

# 3. Install dependencies
pip install -r requirements.txt
```

### Configuration

1. **Copy example configs:**
```bash
cp config/config.example.json config/config.json
cp config/.env.example config/.env
```

2. **Edit `config.json`:**
```json
{
}
```

3. **Edit `.env`:**
```
DB_USER=myuser
DB_PASSWORD=mypass
API_KEY=myapikey
```

---

## 🏃 Running the Application

### Command Line Mode

```bash
# Basic import
python src/main.py --file data/articles.csv --mapping standard

# With custom config
python src/main.py --file data/articles.csv --config config/custom.json

# Dry run (preview only)
python src/main.py --file data/articles.csv --dry-run

# Help
python src/main.py --help
```

### Web UI Mode

```bash
# Start web interface
python src/web_ui.py

# Access at: http://localhost:8000
```

### Build EXE

```bash
# Using PyInstaller
pyinstaller --onefile --windowed --name myfactory-import src/main.py

# Output: dist/myfactory-import.exe
```

---

## 📝 Logging

- Logs stored in `logs/import_YYYY-MM-DD.log`
- Log levels: INFO, WARNING, ERROR
- Summary report generated after each import

---

## 🔧 Key Dependencies

```
fastapi==0.115.6
uvicorn==0.34.0
python-dotenv==1.0.1
pydantic==2.10.4
sqlalchemy==2.0.37
pyodbc==5.2.0
pandas==2.2.3
pyinstaller==6.11.1
```

---

## 📦 Deployment

1. Build EXE: `pyinstaller --onefile --windowed src/main.py`
2. Copy `dist/main.exe` to target Windows VM
3. Ensure `config/` and `.env` are in same directory
4. Run: `myfactory-import.exe --file data.csv`

---

## 🧪 Testing

```bash
# Unit tests
pytest tests/

# Test import (dry run)
python src/main.py --file sample.csv --dry-run

# Validate config
python src/main.py --validate-config
```

---

## 🔒 Security Notes

- Never commit `.env` to version control
- Use environment variables in production
- Encrypt sensitive configs if needed

---

**Ready to start!** 🚀