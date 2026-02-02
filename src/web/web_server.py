"""
FastAPI Web Server for Configuration Management
"""
import os
import logging
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from .config_api import router as config_router

logger = logging.getLogger(__name__)

# Get paths
BASE_DIR = Path(__file__).parent.parent.parent
WEB_DIR = BASE_DIR / "web"


def create_app() -> FastAPI:
    """Create and configure FastAPI application"""
    app = FastAPI(
        title="TelegramAssistant Config Manager",
        description="Web interface for managing TelegramAssistant configuration",
        version="1.0.0",
    )

    # Include API routes
    app.include_router(config_router, prefix="/api")

    # Serve static files
    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/")
        async def serve_index():
            """Serve the main configuration page"""
            index_path = WEB_DIR / "index.html"
            if index_path.exists():
                return FileResponse(str(index_path))
            return {"error": "index.html not found"}

    return app


async def run_server(host: str = "127.0.0.1", port: int = 12321):
    """Run the web server"""
    import uvicorn

    app = create_app()
    config = uvicorn.Config(app, host=host, port=port, log_level="info")
    server = uvicorn.Server(config)
    logger.info(f"Starting web server at http://{host}:{port}")
    await server.serve()
