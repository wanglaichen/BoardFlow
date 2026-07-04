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


class AppConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "boardflow-dev")
    APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
    APP_PORT = int(os.getenv("APP_PORT", os.getenv("PORT", "9213")))
    DATA_DIR = str(DATA_PATH)
    STORAGE_FILE = str(DATA_PATH / "boards.json")
    STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "auto")
    REDIS_URL = os.getenv("REDIS_URL", "")
    REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "jjob:boardflow:state")
    REDIS_SETTINGS_KEY = os.getenv("REDIS_SETTINGS_KEY", "jjob:boardflow:settings")
    REDIS_TIMEOUT_SECONDS = float(os.getenv("REDIS_TIMEOUT_SECONDS", "5"))
