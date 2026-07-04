from flask import Blueprint, abort, render_template, request

from routes.helpers import find_card_on_board
from services.card_editors import get_editor_config

pages_bp = Blueprint("pages", __name__)


def init_pages(board_service):
    @pages_bp.route("/")
    def index():
        return render_template("index.html")

    @pages_bp.route("/board/<board_id>/card/<card_id>/<editor_key>")
    def card_editor_page(board_id: str, card_id: str, editor_key: str):
        config = get_editor_config(editor_key)
        card = find_card_on_board(board_service, board_id, card_id)
        if not card:
            abort(404)

        return_url = request.args.get("from") or f"#/board/{board_id}"
        return render_template(
            config["template"],
            board_id=board_id,
            card_id=card_id,
            card_title=card.get("title") or config["default_title"],
            return_url=return_url,
            editor_key=editor_key,
            static_app=config["static_app"],
        )

    return pages_bp
