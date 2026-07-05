import json

from flask import Blueprint, Response, jsonify, request, send_file, stream_with_context
from io import BytesIO

from services.card_editors import get_editor_config

api_bp = Blueprint("api", __name__)


def init_api(board_service, auth_service, user_service, share_service):
    def _owner_hint() -> dict | None:
        owner_tenant_type = request.args.get("owner_tenant_type") or request.headers.get("X-Board-Owner-Type")
        owner_tenant_id = request.args.get("owner_tenant_id") or request.headers.get("X-Board-Owner-Id")
        if owner_tenant_type and owner_tenant_id:
            return {"owner_tenant_type": owner_tenant_type, "owner_tenant_id": owner_tenant_id}
        return None

    def _with_board_access(board_id: str, *, require_edit: bool = False):
        user = auth_service.require_user()
        access = share_service.resolve_board_access(board_id, user, _owner_hint())
        if require_edit:
            share_service.assert_board_permission(access, "edit")
        elif not access.get("is_owner"):
            share_service.assert_board_permission(access, "view")
        board_service.set_board_access(access)
        return access

    def _require_super_admin():
        auth_service.require_super_admin()

    @api_bp.route("/version", methods=["GET"])
    def get_version():
        from config import format_app_version_label, read_app_version

        version = read_app_version()
        return jsonify(
            {
                "name": "BoardFlow",
                "version": version,
                "label": format_app_version_label(version),
            }
        )

    @api_bp.route("/settings", methods=["GET"])
    def get_settings():
        return jsonify(board_service.get_settings())

    @api_bp.route("/settings/board-statuses", methods=["PUT"])
    def update_board_statuses():
        _require_super_admin()
        payload = request.get_json(silent=True) or {}
        statuses = payload.get("board_statuses") or payload.get("items") or []
        settings = board_service.update_board_statuses(statuses)
        return jsonify({"message": "看板状态已保存", "settings": settings})

    @api_bp.route("/settings/organizations", methods=["PUT"])
    def update_organizations():
        _require_super_admin()
        payload = request.get_json(silent=True) or {}
        organizations = payload.get("organizations") or payload.get("items") or []
        settings = board_service.update_organizations(organizations)
        return jsonify({"message": "组织列表已保存", "settings": settings})

    @api_bp.route("/settings/my-organizations", methods=["PUT"])
    def update_my_organizations():
        auth_service.require_user()
        payload = request.get_json(silent=True) or {}
        organizations = payload.get("organizations") or payload.get("items") or []
        settings = board_service.update_my_organizations(organizations)
        return jsonify({"message": "我的项目组织已保存", "settings": settings})

    @api_bp.route("/settings/editable-fonts", methods=["PUT"])
    def update_editable_fonts():
        _require_super_admin()
        payload = request.get_json(silent=True) or {}
        fonts = payload.get("editable_fonts") or payload
        settings = board_service.update_editable_fonts(fonts)
        return jsonify({"message": "字体设置已保存", "settings": settings})

    @api_bp.route("/users", methods=["GET"])
    def list_users():
        _require_super_admin()
        return jsonify({"items": user_service.list_users()})

    @api_bp.route("/users", methods=["POST"])
    def create_user():
        _require_super_admin()
        payload = request.get_json(silent=True) or {}
        item = user_service.create_user(payload)
        return jsonify({"message": "用户已创建", "item": item})

    @api_bp.route("/users/<user_id>", methods=["PATCH"])
    def update_user(user_id: str):
        _require_super_admin()
        payload = request.get_json(silent=True) or {}
        item = user_service.update_user(user_id, payload)
        return jsonify({"message": "用户已更新", "item": item})

    @api_bp.route("/users/<user_id>", methods=["DELETE"])
    def delete_user(user_id: str):
        _require_super_admin()
        user_service.delete_user(user_id)
        return jsonify({"message": "用户已删除", "id": user_id})

    @api_bp.route("/users/search", methods=["GET"])
    def search_users():
        user = auth_service.require_user()
        query = request.args.get("q", "")
        return jsonify({"items": user_service.search_users(query, user["id"])})

    @api_bp.route("/users/friends", methods=["GET"])
    def list_friends():
        user = auth_service.require_user()
        return jsonify({"items": user_service.list_friends(user["id"])})

    @api_bp.route("/users/friends", methods=["POST"])
    def add_friend():
        user = auth_service.require_user()
        payload = request.get_json(silent=True) or {}
        items = user_service.add_friend(user["id"], payload.get("username") or "")
        return jsonify({"message": "好友已添加", "items": items})

    @api_bp.route("/users/friends/<friend_user_id>", methods=["DELETE"])
    def remove_friend(friend_user_id: str):
        user = auth_service.require_user()
        items = user_service.remove_friend(user["id"], friend_user_id)
        return jsonify({"message": "好友已移除", "items": items})

    @api_bp.route("/shares", methods=["GET"])
    def list_shares():
        user = auth_service.require_user()
        board_id = request.args.get("board_id")
        if board_id:
            tenant = auth_service.get_current_tenant()
            return jsonify({"items": share_service.list_board_shares(tenant, board_id)})
        return jsonify({"items": share_service.list_received_shares(user["id"])})

    @api_bp.route("/shares", methods=["POST"])
    def create_share():
        user = auth_service.require_user()
        payload = request.get_json(silent=True) or {}
        board_id = str(payload.get("board_id") or "")
        grantee_user_id = str(payload.get("grantee_user_id") or "")
        if not board_id or not grantee_user_id:
            raise ValueError("看板与目标用户不能为空")
        _with_board_access(board_id, require_edit=True)
        share = share_service.create_share(
            auth_service.get_current_tenant(),
            board_id,
            grantee_user_id,
            payload.get("permissions") or {},
        )
        return jsonify({"message": "分享已创建", "item": share})

    @api_bp.route("/shares/<share_id>", methods=["PATCH"])
    def update_share(share_id: str):
        auth_service.require_user()
        payload = request.get_json(silent=True) or {}
        share = share_service.update_share(share_id, payload.get("permissions") or {})
        return jsonify({"message": "分享已更新", "item": share})

    @api_bp.route("/shares/<share_id>", methods=["DELETE"])
    def delete_share(share_id: str):
        auth_service.require_user()
        share_service.delete_share(share_id)
        return jsonify({"message": "分享已删除", "id": share_id})

    @api_bp.route("/boards/shared", methods=["GET"])
    def list_shared_boards():
        user = auth_service.require_user()
        return jsonify({"items": share_service.list_shared_boards(user)})

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
        access = _with_board_access(board_id)
        detail = board_service.get_board_detail(board_id)
        if access.get("shared"):
            detail["shared"] = True
            detail["share_permissions"] = access.get("permissions")
            detail["owner_tenant_type"] = access["tenant_ctx"].get("type")
            detail["owner_tenant_id"] = access["tenant_ctx"].get("id")
        return jsonify(detail)

    @api_bp.route("/boards/<board_id>", methods=["PATCH"])
    def update_board(board_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.update_board(board_id, payload)
        return jsonify({"message": "看板已更新", "item": item})

    @api_bp.route("/boards/<board_id>", methods=["DELETE"])
    def delete_board(board_id: str):
        _with_board_access(board_id, require_edit=True)
        result = board_service.delete_board(board_id)
        return jsonify({"message": "看板已删除", **result})

    @api_bp.route("/boards/<board_id>/lists", methods=["POST"])
    def create_list(board_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.create_list(board_id, payload)
        return jsonify({"message": "列表已创建", "item": item})

    @api_bp.route("/boards/<board_id>/lists/<list_id>", methods=["PATCH"])
    def update_list(board_id: str, list_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.update_list(board_id, list_id, payload)
        return jsonify({"message": "列表已更新", "item": item})

    @api_bp.route("/boards/<board_id>/lists/<list_id>", methods=["DELETE"])
    def delete_list(board_id: str, list_id: str):
        _with_board_access(board_id, require_edit=True)
        result = board_service.delete_list(board_id, list_id)
        return jsonify({"message": "列表已删除", **result})

    @api_bp.route("/boards/<board_id>/lists/reorder", methods=["POST"])
    def reorder_lists(board_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        ordered_ids = payload.get("ordered_ids") or []
        items = board_service.reorder_lists(board_id, [str(item) for item in ordered_ids])
        return jsonify({"message": "列表顺序已更新", "items": items})

    @api_bp.route("/boards/<board_id>/lists/<list_id>/cards", methods=["POST"])
    def create_card(board_id: str, list_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.create_card(board_id, list_id, payload)
        return jsonify({"message": "卡片已创建", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>", methods=["PATCH"])
    def update_card(board_id: str, card_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.update_card(board_id, card_id, payload)
        return jsonify({"message": "卡片已更新", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>", methods=["DELETE"])
    def delete_card(board_id: str, card_id: str):
        _with_board_access(board_id, require_edit=True)
        result = board_service.delete_card(board_id, card_id)
        return jsonify({"message": "卡片已删除", **result})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/move", methods=["POST"])
    def move_card(board_id: str, card_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        target_list_id = str(payload.get("list_id") or "")
        target_position = int(payload.get("position", 0))
        if not target_list_id:
            raise ValueError("目标列表不能为空")
        item = board_service.move_card(board_id, card_id, target_list_id, target_position)
        return jsonify({"message": "卡片已移动", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/comments", methods=["POST"])
    def add_comment(board_id: str, card_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.add_comment(board_id, card_id, payload)
        return jsonify({"message": "评论已添加", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/comments/<comment_id>", methods=["PATCH"])
    def update_comment(board_id: str, card_id: str, comment_id: str):
        _with_board_access(board_id, require_edit=True)
        payload = request.get_json(silent=True) or {}
        item = board_service.update_comment(board_id, card_id, comment_id, payload)
        return jsonify({"message": "评论已更新", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/comments/<comment_id>", methods=["DELETE"])
    def delete_comment(board_id: str, card_id: str, comment_id: str):
        _with_board_access(board_id, require_edit=True)
        item = board_service.delete_comment(board_id, card_id, comment_id)
        return jsonify({"message": "评论已删除", "item": item})

    @api_bp.route("/boards/<board_id>/cards/<card_id>/<editor_key>", methods=["GET"])
    def get_card_editor(board_id: str, card_id: str, editor_key: str):
        _with_board_access(board_id)
        config = get_editor_config(editor_key)
        payload = board_service.get_card_editor(board_id, card_id, config["field"])
        return jsonify(payload)

    @api_bp.route("/boards/<board_id>/cards/<card_id>/<editor_key>", methods=["PUT"])
    def save_card_editor(board_id: str, card_id: str, editor_key: str):
        _with_board_access(board_id, require_edit=True)
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
        _require_super_admin()
        content, filename = board_service.export_system_dat()
        return send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    @api_bp.route("/data-transfer/export/organization/<org_id>", methods=["GET"])
    def export_organization_dat(org_id: str):
        user = auth_service.require_user()
        owner_only = request.args.get("scope") == "owner" or not user.get("is_super_admin")
        if owner_only:
            board_service.assert_org_owner(org_id)
        content, filename = board_service.export_organization_dat(org_id, owner_only=owner_only)
        return send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    @api_bp.route("/data-transfer/export/board/<board_id>", methods=["GET"])
    def export_board_dat(board_id: str):
        access = _with_board_access(board_id)
        if not access.get("is_owner"):
            return jsonify({"message": "仅看板创建者可导出"}), 403
        content, filename = board_service.export_board_dat(board_id)
        return send_file(
            BytesIO(content),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    @api_bp.route("/data-transfer/validate", methods=["POST"])
    def validate_import_dat():
        auth_service.require_user()
        raw = _read_uploaded_dat(request)
        expected_kind = (request.form.get("expected_kind") or request.args.get("expected_kind") or "").strip() or None
        try:
            result = board_service.validate_import_dat(raw, expected_kind=expected_kind)
        except PermissionError as error:
            return jsonify({"message": str(error)}), 403
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        return jsonify(result)

    @api_bp.route("/data-transfer/import", methods=["POST"])
    def import_dat():
        user = auth_service.require_user()
        raw = _read_uploaded_dat(request)
        mode = (request.form.get("mode") or "merge").strip()
        expected_kind = (request.form.get("expected_kind") or "").strip() or None
        owner_only = request.form.get("owner_only") == "1" or not user.get("is_super_admin")
        try:
            validation = board_service.validate_import_dat(raw, expected_kind=expected_kind)
        except PermissionError as error:
            return jsonify({"message": str(error)}), 403
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        if not validation.get("valid"):
            return jsonify({"message": "数据包校验未通过", "validation": validation}), 400
        try:
            validation = board_service.import_dat(raw, mode=mode, owner_only=owner_only)
        except PermissionError as error:
            return jsonify({"message": str(error)}), 403
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        return jsonify({"message": "数据导入成功", "validation": validation})

    @api_bp.route("/data-transfer/clear-system", methods=["POST"])
    def clear_system_data():
        _require_super_admin()

        @stream_with_context
        def generate():
            try:
                for event in board_service.iter_clear_all_system_data():
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except Exception as error:
                payload = {
                    "step": "error",
                    "message": str(error) or "清理失败",
                    "percent": 0,
                    "done": True,
                    "error": True,
                }
                yield json.dumps(payload, ensure_ascii=False) + "\n"

        return Response(generate(), mimetype="application/x-ndjson")

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
