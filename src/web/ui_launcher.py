"""Web UI launcher."""

import socket
import sys
import threading
import time
import webbrowser

from src.config_manager import get_config_manager


def find_available_port(start_port: int = 8000) -> int:
    """Find the first available port starting from start_port."""
    port = start_port
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                port += 1


def launch_web_ui():
    """Launch the FastAPI server and open browser."""
    try:
        import uvicorn
    except ImportError:
        print(
            "❌ FastAPI is not installed. Run: pip install fastapi uvicorn python-multipart"
        )
        sys.exit(1)

    # Check if configured
    config = get_config_manager()
    if not config.is_configured():
        print("🔐 Database not configured. Starting setup...")
        config.interactive_setup()
        if not config.is_configured():
            print("❌ Setup cancelled or failed. Exiting.")
            sys.exit(1)

    port = find_available_port(8000)

    print(f"\n{'='*60}")
    print(f"🚀 MyFactory Import Tool - Web UI")
    print(f"{'='*60}")
    print(f"✅ Starting server at: http://127.0.0.1:{port}")
    print(f"📚 API docs at: http://127.0.0.1:{port}/docs")
    print(f"{'='*60}\n")

    def run_server():
        from src.web.app import create_app

        app = create_app()
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{port}")
    print("🌐 Browser opened to Web UI")
    print("Press Ctrl+C to stop the server\n")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n🛑 Shutting down server...")
        sys.exit(0)
