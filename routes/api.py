from flask import Blueprint, jsonify, request, send_file
from io import BytesIO

from services.card_editors import get_editor_config
api_bp = Blueprint("api", __name__)


def init_api(board_service):
    @api_bp.route("/settings", methods=["GET"])
    def get_settings():
        return jsonify(board_service.get_settings())

    @api_bp.route("/settings/board-statuses", methods=["PUT"])
    def update_board_statuses():
        payload = request.get_json(silent=True) or {}
        statuses = payload.get("board_statuses") or payload.get("items") or []
        settings = board_service.update_board_statuses(statuses)
        return jsonify({"message": "看板状态已保存", "settings": settings})

    @api_bp.route("/settings/organizations", methods=["PUT"])
    def update_organizations():
        payload = request.get_json(silent=True) or {}
        organizations = payload.get("organizations") or payload.get("items") or []
        settings = board_service.update_organizations(organizations)
        return jsonify({"message": "组织列表已保存", "settings": settings})

    @api_bp.route("/settings/editable-fonts", methods=["PUT"])
    def update_editable_fonts():
        payload = request.get_json(silent=True) or {}
        fonts = payload.get("editable_fonts") or payload
        settings = board_service.update_editable_fonts(fonts)
        return jsonify({"message": "字体设置已保存", "settings": settings})

    @api_bp.route("/boards", methods=["GET"])
    def list_boards():
        return jsonify({"items": board_service.list_boards()})

    @api_bp.route("/boards", methods=["POST"])
    def create_board():
        payload = request.get_json(silent=True) or {}
        item = board_service.create_board(payload)
        return jsonify({"message": "看板已创建", "item": item})

    @api_bp.route("/boards/<board_id>", methods=["GET"])
    def get_board(board_id: str):
        return jsonify(board_service.get_board_detail(board_id))

    @api_bp.route("/boards/<board_id>", methods=["PATCH"])
    def update_board(board_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.update_board(board_id, payload)
        return jsonify({"message": "看板已更新", "item": item})

    @api_bp.route("/boards/<board_id>", methods=["DELETE"])
    def delete_board(board_id: str):
        result = board_service.delete_board(board_id)
        return jsonify({"message": "看板已删除", **result})

    @api_bp.route("/boards/<board_id>/lists", methods=["POST"])
    def create_list(board_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.create_list(board_id, payload)
        return jsonify({"message": "列表已创建", "item": item})

    @api_bp.route("/boards/<board_id>/lists/<list_id>", methods=["PATCH"])
    def update_list(board_id: str, list_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.update_list(board_id, list_id, payload)
        return jsonify({"message": "列表已更新", "item": item})

    @api_bp.route("/boards/<board_id>/lists/<list_id>", methods=["DELETE"])
    def delete_list(board_id: str, list_id: str):
        result = board_service.delete_list(board_id, list_id)
        return jsonify({"message": "列表已删除", **result})

    @api_bp.route("/boards/<board_id>/lists/reorder", methods=["POST"])
    def reorder_lists(board_id: str):
        payload = request.get_json(silent=True) or {}
        ordered_ids = payload.get("ordered_ids") or []
        items = board_service.reorder_lists(board_id, [str(item) for item in ordered_ids])
        return jsonify({"message": "列表顺序已更新", "items": items})

    @api_bp.route("/boards/<board_id>/lists/<list_id>/cards", methods=["POST"])
    def create_card(board_id: str, list_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.create_card(board_id, list_id, payload)
        return jsonify({"message": "卡片已创建", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>", methods=["PATCH"])
    def update_card(board_id: str, card_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.update_card(board_id, card_id, payload)
        return jsonify({"message": "卡片已更新", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>", methods=["DELETE"])
    def delete_card(board_id: str, card_id: str):
        result = board_service.delete_card(board_id, card_id)
        return jsonify({"message": "卡片已删除", **result})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/move", methods=["POST"])
    def move_card(board_id: str, card_id: str):
        payload = request.get_json(silent=True) or {}
        target_list_id = str(payload.get("list_id") or "")
        target_position = int(payload.get("position", 0))
        if not target_list_id:
            raise ValueError("目标列表不能为空")
        item = board_service.move_card(board_id, card_id, target_list_id, target_position)
        return jsonify({"message": "卡片已移动", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/comments", methods=["POST"])
    def add_comment(board_id: str, card_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.add_comment(board_id, card_id, payload)
        return jsonify({"message": "评论已添加", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/comments/<comment_id>", methods=["PATCH"])
    def update_comment(board_id: str, card_id: str, comment_id: str):
        payload = request.get_json(silent=True) or {}
        item = board_service.update_comment(board_id, card_id, comment_id, payload)
        return jsonify({"message": "评论已更新", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/comments/<comment_id>", methods=["DELETE"])
    def delete_comment(board_id: str, card_id: str, comment_id: str):
        item = board_service.delete_comment(board_id, card_id, comment_id)
        return jsonify({"message": "评论已删除", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/<editor_key>", methods=["GET"])
    def get_card_editor(board_id: str, card_id: str, editor_key: str):
        config = get_editor_config(editor_key)
        payload = board_service.get_card_editor(board_id, card_id, config["field"])
        return jsonify(payload)

    @api_bp.route("/boards/<board_id>/cards/<card_id>/<editor_key>", methods=["PUT"])
    def save_card_editor(board_id: str, card_id: str, editor_key: str):
        config = get_editor_config(editor_key)
        payload = request.get_json(silent=True) or {}
        item = board_service.update_card_editor(board_id, card_id, config["field"], payload.get(config["field"]))
        return jsonify({"message": config["save_message"], "item": item})

    @api_bp.route("/search", methods=["GET"])
    def search():
        keyword = request.args.get("q", "")
        return jsonify(board_service.search(keyword))

    @api_bp.route("/data-transfer/export/system", methods=["GET"])
    def export_system_dat():
        content, filename = board_service.export_system_dat()
        return send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    @api_bp.route("/data-transfer/export/organization/<org_id>", methods=["GET"])
    def export_organization_dat(org_id: str):
        content, filename = board_service.export_organization_dat(org_id)
        return send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    @api_bp.route("/data-transfer/export/board/<board_id>", methods=["GET"])
    def export_board_dat(board_id: str):
        content, filename = board_service.export_board_dat(board_id)
        return send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    @api_bp.route("/data-transfer/validate", methods=["POST"])
    def validate_import_dat():
        raw = _read_uploaded_dat(request)
        expected_kind = (request.form.get("expected_kind") or request.args.get("expected_kind") or "").strip() or None
        result = board_service.validate_import_dat(raw, expected_kind=expected_kind)
        return jsonify(result)

    @api_bp.route("/data-transfer/import", methods=["POST"])
    def import_dat():
        raw = _read_uploaded_dat(request)
        mode = (request.form.get("mode") or "merge").strip()
        expected_kind = (request.form.get("expected_kind") or "").strip() or None
        validation = board_service.validate_import_dat(raw, expected_kind=expected_kind)
        if not validation.get("valid"):
            return jsonify({"message": "数据包校验未通过", "validation": validation}), 400
        validation = board_service.import_dat(raw, mode=mode)
        return jsonify({"message": "数据导入成功", "validation": validation})

    return api_bp


def _read_uploaded_dat(request) -> bytes:
    upload = request.files.get("file")
    if upload:
        raw = upload.read()
        if not raw:
            raise ValueError("上传文件为空")
        return raw
    payload = request.get_json(silent=True) or {}
    content = payload.get("content")
    if isinstance(content, str) and content.strip():
        return content.encode("utf-8")
    raise ValueError("请上传 .dat 文件")
