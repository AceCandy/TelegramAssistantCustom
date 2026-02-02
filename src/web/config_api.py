"""
Configuration API Routes
"""
import os
import yaml
import logging
from pathlib import Path
from typing import Any, Dict
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["config"])

# Config file path
BASE_DIR = Path(__file__).parent.parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.yaml"


class ConfigUpdateRequest(BaseModel):
    """Request model for config updates"""
    config: Dict[str, Any]


class ConfigResponse(BaseModel):
    """Response model for config"""
    success: bool
    config: Dict[str, Any] | None = None
    message: str = ""


def load_config_file() -> Dict[str, Any]:
    """Load configuration from YAML file"""
    if not CONFIG_FILE.exists():
        raise HTTPException(status_code=404, detail="Configuration file not found")
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config
    except Exception as e:
        logger.error(f"Error loading config: {e}")
        raise HTTPException(status_code=500, detail=f"Error loading config: {str(e)}")


def save_config_file(config: Dict[str, Any]) -> None:
    """Save configuration to YAML file"""
    try:
        # Ensure config directory exists
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
    except Exception as e:
        logger.error(f"Error saving config: {e}")
        raise HTTPException(status_code=500, detail=f"Error saving config: {str(e)}")


def validate_config(config: Dict[str, Any]) -> tuple[bool, str]:
    """Validate configuration structure"""
    errors = []
    
    # Check required fields
    if not config.get("api_id"):
        errors.append("api_id is required")
    if not config.get("api_hash"):
        errors.append("api_hash is required")
    if not config.get("bot_account", {}).get("token"):
        errors.append("bot_account.token is required")
    
    # Validate proxy port if enabled
    proxy = config.get("proxy", {})
    if proxy.get("enabled"):
        if not proxy.get("host"):
            errors.append("proxy.host is required when proxy is enabled")
        port = proxy.get("port")
        if not isinstance(port, int) or port < 1 or port > 65535:
            errors.append("proxy.port must be a valid port number (1-65535)")
    
    if errors:
        return False, "; ".join(errors)
    return True, "Configuration is valid"


@router.get("/config", response_model=ConfigResponse)
async def get_config():
    """Get current configuration"""
    try:
        config = load_config_file()
        return ConfigResponse(success=True, config=config)
    except HTTPException:
        raise
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@router.put("/config", response_model=ConfigResponse)
async def update_config(request: ConfigUpdateRequest):
    """Update configuration"""
    try:
        # Validate configuration
        is_valid, message = validate_config(request.config)
        if not is_valid:
            return ConfigResponse(success=False, message=f"Validation failed: {message}")
        
        # Save configuration
        save_config_file(request.config)
        
        return ConfigResponse(
            success=True,
            config=request.config,
            message="Configuration saved successfully. Restart the bot for changes to take effect."
        )
    except HTTPException:
        raise
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))


@router.get("/config/validate", response_model=ConfigResponse)
async def validate_current_config():
    """Validate current configuration"""
    try:
        config = load_config_file()
        is_valid, message = validate_config(config)
        return ConfigResponse(success=is_valid, config=config, message=message)
    except HTTPException:
        raise
    except Exception as e:
        return ConfigResponse(success=False, message=str(e))
