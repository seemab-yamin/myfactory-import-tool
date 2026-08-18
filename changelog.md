# CHANGELOG

## [Unreleased]

### Added
- Project scaffolding with modular structure (`src/`, `config/`, `templates/`)
- CLI entry point (`src/main.py`) with argument parsing (`--file`, `--mapping`, `--dry-run`, `--batch`, `--validate-config`, `--verbose`)
- Configuration management (`src/config_manager.py`) with JSON and `.env` support
- Core import logic (`src/importer.py`) with CSV reading, delimiter detection, and dry-run mode
- Field mapping (`src/mapper.py`) for CSV-to-Myfactory field transformation
- Logging system (`src/logger.py`) with file and console handlers
- Data models (`src/models.py`) for import status and results
- Web UI placeholder (`src/web_ui.py` and `templates/index.html`)
- Example configuration files (`config/config.example.json`, `config/.env.example`)
- Dependencies list (`requirements.txt`) with pandas, python-dotenv, pydantic, etc.
- PyInstaller setup (`setup.py`) for EXE packaging
- `.gitignore` and `README.md`