import json

from flask import Blueprint, Response, jsonify, request, stream_with_context


def init_compare(compare_service, auth_service):
    bp = Blueprint("compare", __name__)

    def _require_super_admin():
        auth_service.require_super_admin()

    @bp.route("/sessions", methods=["POST"])
    def create_compare_session():
        _require_super_admin()
        payload = request.get_json(silent=True) or {}
        try:
            result = compare_service.create_session(payload)
        except ValueError as error:
            return jsonify({"message": str(error)}), 400
        return jsonify(result), 201

    @bp.route("/sessions/<session_id>", methods=["GET"])
    def get_compare_session(session_id: str):
        _require_super_admin()
        session = compare_service.get_session(session_id)
        if not session:
            return jsonify({"message": "对比会话不存在或已过期"}), 404
        return jsonify(session)

    @bp.route("/sessions/<session_id>", methods=["DELETE"])
    def delete_compare_session(session_id: str):
        _require_super_admin()
        if not compare_service.delete_session(session_id):
            return jsonify({"message": "对比会话不存在或已过期"}), 404
        return jsonify({"message": "对比会话已删除"})

    @bp.route("/sessions/<session_id>/run", methods=["POST"])
    def run_compare_session(session_id: str):
        _require_super_admin()
        run_options = request.get_json(silent=True) or {}

        @stream_with_context
        def generate():
            try:
                for event in compare_service.iter_run_session(session_id, run_options=run_options):
                    yield json.dumps(event, ensure_ascii=False) + "\n"
            except ValueError as error:
                payload = {
                    "step": "error",
                    "message": str(error),
                    "percent": 0,
                    "done": True,
                    "error": True,
                    "fatal": True,
                }
                yield json.dumps(payload, ensure_ascii=False) + "\n"
            except Exception as error:
                payload = {
                    "step": "error",
                    "message": str(error) or "对比失败",
                    "percent": 0,
                    "done": True,
                    "error": True,
                    "fatal": True,
                }
                yield json.dumps(payload, ensure_ascii=False) + "\n"

        return Response(generate(), mimetype="application/x-ndjson")

    @bp.route("/sessions/<session_id>/results", methods=["GET"])
    def get_compare_session_results(session_id: str):
        _require_super_admin()
        pair_index_raw = request.args.get("pair_index")
        pair_index = int(pair_index_raw) if pair_index_raw is not None else None
        section = (request.args.get("section") or "").strip() or None
        list_id = (request.args.get("list_id") or "").strip() or None
        offset = request.args.get("offset", type=int) or 0
        limit = request.args.get("limit", type=int)
        try:
            result = compare_service.get_session_results(
                session_id,
                pair_index=pair_index,
                section=section,
                list_id=list_id,
                offset=offset,
                limit=limit,
            )
        except ValueError as error:
            return jsonify({"message": str(error)}), 404
        return jsonify(result)

    return bp
