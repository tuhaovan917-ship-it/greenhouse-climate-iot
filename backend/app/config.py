"""Runtime configuration loaded from environment variables.

Kept dependency-free (no pydantic-settings) so the demo runs with plain
`python-dotenv` + a dataclass. Values follow docs/api-contract.md v0.2.2.
"""

import os
from dataclasses import dataclass, field
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

DEFAULT_DEVICE_ID = "greenhouse-01"


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class MqttSettings:
    url: str = "mqtt://localhost:1883"
    username: str = ""
    password: str = ""
    ca_file: str | None = None
    client_id: str = "greenhouse-backend"
    keepalive: int = 30
    enabled: bool = True

    @property
    def host(self) -> str:
        return urlparse(self.url).hostname or "localhost"

    @property
    def port(self) -> int:
        parsed = urlparse(self.url)
        if parsed.port:
            return parsed.port
        return 8883 if parsed.scheme in {"mqtts", "tls", "ssl"} else 1883

    @property
    def use_tls(self) -> bool:
        return urlparse(self.url).scheme in {"mqtts", "tls", "ssl"}


@dataclass(frozen=True)
class Settings:
    database_url: str = "sqlite:///./greenhouse.db"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    device_id: str = DEFAULT_DEVICE_ID
    # Empty API key disables write protection (localhost demo). See contract section 5.
    api_key: str = ""
    # Cookie Secure must be True for HTTPS deployment. False only for localhost.
    auth_cookie_secure: bool = False
    auth_session_hours: int = 8
    cors_origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173")
    # No ESP32 reply within this many seconds -> command becomes TIMEOUT (contract 3.5).
    command_timeout_s: int = 5
    # No valid MQTT message from a device for this many seconds -> online=false (contract 3.4).
    device_timeout_s: int = 15
    mqtt: MqttSettings = field(default_factory=MqttSettings)
    # Max raw rows scanned per history query before bucket aggregation (contract 3.2).
    # The ESP32 publishes every 2s -> ~43k rows for 24h, so keep the limit above
    # that; wider ranges must use a bucket (1m/5m/1h).
    max_scan_rows: int = 50000
    # Rows kept in memory as recent telemetry cache for /latest fallback.
    telemetry_cache_size: int = 500
    # Dev/demo only: create missing tables at startup instead of running
    # `alembic upgrade head` from database/ (owner: Member 3). Keep 0 in CI.
    auto_create_tables: bool = False


def load_settings() -> Settings:
    mqtt = MqttSettings(
        url=os.getenv("MQTT_URL", MqttSettings.url) or MqttSettings.url,
        username=os.getenv("MQTT_USERNAME", "") or "",
        password=os.getenv("MQTT_PASSWORD", "") or "",
        ca_file=os.getenv("MQTT_CA_FILE") or None,
        client_id=os.getenv("MQTT_CLIENT_ID", MqttSettings.client_id)
        or MqttSettings.client_id,
        keepalive=_read_int("MQTT_KEEPALIVE_S", MqttSettings.keepalive),
        enabled=_read_bool("MQTT_ENABLED", True),
    )
    return Settings(
        database_url=os.getenv("DATABASE_URL", Settings.database_url)
        or Settings.database_url,
        api_host=os.getenv("API_HOST", Settings.api_host) or Settings.api_host,
        api_port=_read_int("API_PORT", Settings.api_port),
        device_id=os.getenv("DEVICE_ID", Settings.device_id) or Settings.device_id,
        api_key=os.getenv("API_KEY", "") or "",
        auth_cookie_secure=_read_bool("AUTH_COOKIE_SECURE", False),
        auth_session_hours=max(1, min(24, _read_int("AUTH_SESSION_HOURS", 8))),
        cors_origins=tuple(
            o.strip().rstrip("/") for o in os.getenv(
                "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
            ).split(",") if o.strip()
        ),
        command_timeout_s=_read_int("COMMAND_TIMEOUT_S", 5),
        device_timeout_s=_read_int("DEVICE_TIMEOUT_S", 15),
        mqtt=mqtt,
        max_scan_rows=_read_int("MAX_SCAN_ROWS", Settings.max_scan_rows),
        telemetry_cache_size=_read_int(
            "TELEMETRY_CACHE_SIZE", Settings.telemetry_cache_size
        ),
        auto_create_tables=_read_bool("AUTO_CREATE_TABLES", False),
    )


settings = load_settings()
