# Changelog

## [1.0.0] - 2026-08-18
### Added
- CLI entry point with `--file`, `--mapping`, `--dry-run`, `--validate-config`
- CSV reader with delimiter detection (`,`, `;`, `\t`)
- Field mapping via `config.json` (saved per mapping name)
- Config manager (`config.json` + `.env` secrets)
- Logging with file + console output
- Dry-run preview mode
- `--validate-config` to check setup
- PyInstaller support for EXE builds
- Web UI stub (FastAPI + HTML template)

### Fixed
- Import errors: fixed `Mapping 'default' not found` — ensure `config.json` has `mappings.default`
- Module imports: switched to relative imports (`from config_manager import`)
- Added missing `get_database_config()` method in `ConfigManager`

### Changed
- Default mapping name: `default`
- Logs stored in `logs/import_<timestamp>.log`
