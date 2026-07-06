import os
from pathlib import Path

from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException

from config import AppConfig
from routes.api import init_api
from routes.auth import init_auth
from routes.compare import init_compare
from routes.federation import init_federation
from routes.pages import init_pages
from services.auth_service import AuthService
from services.board_service import BoardService
from services.boardflow_storage import create_boardflow_storage
from services.card_revision import ConflictError
from services.compare_service import CompareService
from services.edit_lock_service import EditLockRequiredError, EditLockService, InvalidLockTokenError, LockHeldError
from services.share_service import ShareService
from services.user_service import UserService

app = Flask(__name__)
app.config.from_object(AppConfig)

STATIC_DIR = Path(app.root_path) / "static"
ASSET_VERSION_FILES = (
    STATIC_DIR / "css" / "main.css",
    STATIC_DIR / "js" / "main.js",
    STATIC_DIR / "js" / "card-description-editor.js",
    STATIC_DIR / "js" / "card-description-editor.css",
    STATIC_DIR / "js" / "card-markdown-editor.js",
    STATIC_DIR / "js" / "card-markdown-editor.css",
    STATIC_DIR / "js" / "card-editors.js",
    STATIC_DIR / "js" / "card-conflict.js",
)


def resolve_asset_version() -> str:
    mtimes = [int(path.stat().st_mtime) for path in ASSET_VERSION_FILES if path.exists()]
    return str(max(mtimes)) if mtimes else "0"


@app.context_processor
def inject_asset_version():
    from config import format_app_version_label, read_app_version

    version = read_app_version()
    return {
        "asset_version": resolve_asset_version(),
        "app_version": version,
        "app_version_label": format_app_version_label(version),
    }

storage = create_boardflow_storage(AppConfig.__dict__)
user_service = UserService(storage, auth_service=None)
auth_service = AuthService(AppConfig.__dict__, user_service)
user_service.auth_service = auth_service
share_service = ShareService(storage, auth_service)
board_service = BoardService(storage, auth_service=auth_service, share_service=share_service)
edit_lock_service = EditLockService(storage, AppConfig.__dict__)
compare_service = CompareService(AppConfig.__dict__, storage)
board_service.seed_demo_if_empty()

with app.app_context():
    board_service._read_admin_organizations()
    for user in storage.list_users():
        user_id = str(user.get("id") or "")
        if user_id:
            board_service._migrate_user_organizations(user_id)
    grantee_ids = {
        str(share.get("grantee_user_id"))
        for share in storage.list_shares()
        if share.get("grantee_user_id")
    }
    for user_id in grantee_ids:
        share_service.sync_grantee_share_index(user_id)

app.register_blueprint(init_pages(board_service, auth_service, share_service))
app.register_blueprint(init_auth(auth_service), url_prefix="/api/auth")
app.register_blueprint(
    init_api(board_service, auth_service, user_service, share_service, edit_lock_service),
    url_prefix="/api",
)
app.register_blueprint(init_federation(storage), url_prefix="/api/federation")
app.register_blueprint(init_compare(compare_service, auth_service), url_prefix="/api/compare")

_storage_label = type(storage).__name__
if getattr(storage, "using_fallback", False):
    print(f"[BoardFlow] storage={_storage_label} (redis unavailable, using JSON fallback)")
elif AppConfig.REDIS_URL and AppConfig.STORAGE_BACKEND != "json":
    print(
        "[BoardFlow] storage=Redis "
        f"prefix={AppConfig.REDIS_KEY_PREFIX} settings={AppConfig.REDIS_SETTINGS_KEY}"
    )
else:
    print(f"[BoardFlow] storage={_storage_label} file={AppConfig.STORAGE_FILE}")


def _is_public_api_path(path: str) -> bool:
    return path in ("/api/auth/login", "/api/version") or path.startswith("/api/federation/")


def _is_public_page_path(path: str) -> bool:
    return path == "/" or path.startswith("/static/")


@app.before_request
def require_authentication():
    if _is_public_page_path(request.path):
        return None
    if request.path.startswith("/api/"):
        if _is_public_api_path(request.path):
            return None
        user = auth_service.get_current_user()
        if not user:
            return jsonify({"message": "请先登录"}), 401
        g.current_user = user
        g.tenant = auth_service.get_current_tenant()
        return None

    if request.path.startswith("/board/"):
        user = auth_service.get_current_user()
        if not user:
            return jsonify({"message": "请先登录"}), 401
        g.current_user = user
        g.tenant = auth_service.get_current_tenant()
    return None


@app.teardown_request
def clear_board_access(_error=None):
    board_service.clear_board_access()


@app.after_request
def disable_browser_cache_for_local_assets(response):
    path = request.path
    if path == "/" or path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


@app.errorhandler(ConflictError)
def handle_conflict_error(error):
    return (
        jsonify(
            {
                "error": "conflict",
                "message": str(error),
                "current": getattr(error, "current", None) or {},
                "base_revision": getattr(error, "base_revision", None),
            }
        ),
        409,
    )


@app.errorhandler(LockHeldError)
def handle_lock_held_error(error):
    return (
        jsonify(
            {
                "error": "locked",
                "message": str(error),
                "holder": getattr(error, "holder", None) or {},
            }
        ),
        409,
    )


@app.errorhandler(EditLockRequiredError)
@app.errorhandler(InvalidLockTokenError)
def handle_edit_lock_error(error):
    return jsonify({"error": "invalid_lock", "message": str(error)}), 423


@app.errorhandler(PermissionError)
def handle_permission_error(error):
    return jsonify({"message": str(error)}), 403


@app.errorhandler(ValueError)
def handle_value_error(error):
    return jsonify({"message": str(error)}), 400


@app.errorhandler(HTTPException)
def handle_http_error(error):
    if request.path.startswith("/api/"):
        return jsonify({"message": error.description}), error.code
    return error


@app.errorhandler(Exception)
def handle_unexpected_error(error):
    app.logger.exception("Unhandled error")
    if request.path.startswith("/api/"):
        return jsonify({"message": str(error)}), 500
    raise error


if __name__ == "__main__":
    debug_enabled = os.getenv("APP_DEBUG", "0") == "1"
    app.run(
        debug=debug_enabled,
        use_reloader=False,
        host=app.config["APP_HOST"],
        port=app.config["APP_PORT"],
    )
