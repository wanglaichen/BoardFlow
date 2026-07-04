import os

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from config import AppConfig
from routes.api import init_api
from routes.pages import init_pages
from services.board_service import BoardService
from services.storage import create_storage

app = Flask(__name__)
app.config.from_object(AppConfig)

storage = create_storage(AppConfig.__dict__)
board_service = BoardService(storage)
board_service.seed_demo_if_empty()

app.register_blueprint(init_pages(board_service))
app.register_blueprint(init_api(board_service), url_prefix="/api")

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
