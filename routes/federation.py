from flask import Blueprint, jsonify, request

from config import AppConfig, read_app_version
from services.federation_service import (
    DEFAULT_ACCOUNTS_PAGE_SIZE,
    DEFAULT_BOARDS_PAGE_SIZE,
    DEFAULT_CARDS_PAGE_SIZE,
    build_health_payload,
    build_tenant_context_for_federation,
    get_federation_board_lists,
    get_federation_board_meta,
    is_federation_enabled,
    paginate_federation_accounts,
    paginate_federation_boards,
    paginate_federation_list_cards,
    verify_federation_token,
)


def init_federation(storage):
    bp = Blueprint("federation", __name__)

    @bp.before_request
    def guard_federation_api():
        if not is_federation_enabled(AppConfig.__dict__):
            return jsonify({"message": "联邦对比 API 未启用"}), 404

        token = request.headers.get("X-Federation-Token")
        if not verify_federation_token(AppConfig.__dict__, token):
            return jsonify({"message": "联邦令牌无效或未配置"}), 401
        return None

    @bp.route("/health", methods=["GET"])
    def federation_health():
        version = read_app_version()
        return jsonify(
            build_health_payload(
                version=version,
                enabled=True,
            )
        )

    @bp.route("/accounts", methods=["GET"])
    def federation_accounts():
        cursor = request.args.get("cursor")
        limit = request.args.get("limit", type=int) or DEFAULT_ACCOUNTS_PAGE_SIZE
        return jsonify(paginate_federation_accounts(storage, cursor=cursor, limit=limit))

    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards", methods=["GET"])
    def federation_account_boards(tenant_type: str, tenant_id: str):
        try:
            build_tenant_context_for_federation(tenant_type, tenant_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        cursor = request.args.get("cursor")
        limit = request.args.get("limit", type=int) or DEFAULT_BOARDS_PAGE_SIZE
        return jsonify(
            paginate_federation_boards(
                storage,
                tenant_type,
                tenant_id,
                cursor=cursor,
                limit=limit,
            )
        )

    @bp.route("/accounts/<tenant_type>/<tenant_id>/board-sync", methods=["POST"])
    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards/sync", methods=["POST"])
    def federation_board_sync(tenant_type: str, tenant_id: str):
        try:
            build_tenant_context_for_federation(tenant_type, tenant_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        body = request.get_json(silent=True) or {}
        sync_payload = body.get("payload")
        if not isinstance(sync_payload, dict):
            return jsonify({"message": "payload 无效"}), 400
        target_board_id = (body.get("target_board_id") or "").strip() or None
        mode = (body.get("mode") or "replace").strip()
        from services.compare_sync import apply_board_sync_payload

        try:
            result = apply_board_sync_payload(
                storage,
                tenant_type,
                tenant_id,
                sync_payload,
                target_board_id=target_board_id,
                mode=mode,
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        return jsonify(result)

    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards/<board_id>", methods=["DELETE"])
    def federation_board_delete(tenant_type: str, tenant_id: str, board_id: str):
        try:
            build_tenant_context_for_federation(tenant_type, tenant_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        from services.compare_sync import delete_board_from_tenant

        try:
            result = delete_board_from_tenant(storage, tenant_type, tenant_id, board_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 404
        return jsonify(result)

    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards/<board_id>/meta", methods=["GET"])
    def federation_board_meta(tenant_type: str, tenant_id: str, board_id: str):
        try:
            return jsonify(get_federation_board_meta(storage, tenant_type, tenant_id, board_id))
        except ValueError as error:
            return jsonify({"message": str(error)}), 404

    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards/<board_id>/lists", methods=["GET"])
    def federation_board_lists(tenant_type: str, tenant_id: str, board_id: str):
        try:
            return jsonify(get_federation_board_lists(storage, tenant_type, tenant_id, board_id))
        except ValueError as error:
            return jsonify({"message": str(error)}), 404

    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards/<board_id>/lists/<list_id>/cards", methods=["GET"])
    def federation_board_list_cards(tenant_type: str, tenant_id: str, board_id: str, list_id: str):
        try:
            build_tenant_context_for_federation(tenant_type, tenant_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        cursor = request.args.get("cursor")
        limit = request.args.get("limit", type=int) or DEFAULT_CARDS_PAGE_SIZE
        include_description = request.args.get("include_description", "").lower() in ("1", "true", "yes")
        try:
            return jsonify(
                paginate_federation_list_cards(
                    storage,
                    tenant_type,
                    tenant_id,
                    board_id,
                    list_id,
                    cursor=cursor,
                    limit=limit,
                    include_description=include_description,
                )
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 404

    @bp.route("/accounts/<tenant_type>/<tenant_id>/boards/<board_id>/export", methods=["GET"])
    def federation_board_export(tenant_type: str, tenant_id: str, board_id: str):
        try:
            build_tenant_context_for_federation(tenant_type, tenant_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        from services.compare_sync import load_board_full_sync_payload

        try:
            payload = load_board_full_sync_payload(storage, tenant_type, tenant_id, board_id)
        except ValueError as error:
            return jsonify({"message": str(error)}), 404
        return jsonify({"payload": payload})

    return bp
