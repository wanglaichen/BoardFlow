import json
import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"


def load_env_file(path: Path = ENV_FILE) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)


load_env_file()


def resolve_data_path() -> Path:
    configured_path = os.getenv("DATA_DIR")
    if configured_path:
        return Path(configured_path)
    if os.getenv("VERCEL"):
        return Path("/tmp/boardflow")
    return BASE_DIR / "data"


DATA_PATH = resolve_data_path()
VERSION_FILE = BASE_DIR / "VERSION"


def read_app_version() -> str:
    override = (os.getenv("APP_VERSION") or "").strip()
    if override:
        return override.lstrip("vV")
    if VERSION_FILE.exists():
        text = VERSION_FILE.read_text(encoding="utf-8").strip()
        if text:
            return text.lstrip("vV")
    return "dev"


def format_app_version_label(version: str | None = None) -> str:
    value = (version if version is not None else read_app_version()).strip() or "dev"
    if value == "dev":
        return "dev"
    return value if value.startswith("v") else f"v{value}"


class AppConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "boardflow-dev")
    APP_VERSION = read_app_version()
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", os.getenv("PORT", "9213")))
    DATA_DIR = str(DATA_PATH)
    STORAGE_FILE = str(DATA_PATH / "boards.json")
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "auto")
    REDIS_URL = os.getenv("REDIS_URL", "")
    REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "jjob:boardflow")
    REDIS_SETTINGS_KEY = os.getenv("REDIS_SETTINGS_KEY", "jjob:boardflow:settings")
    REDIS_TIMEOUT_SECONDS = float(os.getenv("REDIS_TIMEOUT_SECONDS", "5"))
    SUPER_ADMIN_USERNAME = os.getenv("SUPER_ADMIN_USERNAME", "admin")
    SUPER_ADMIN_PASSWORD = os.getenv("SUPER_ADMIN_PASSWORD", "")
    SUPER_ADMIN_PASSWORD_HASH = os.getenv("SUPER_ADMIN_PASSWORD_HASH", "")
