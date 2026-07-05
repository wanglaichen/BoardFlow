from flask import Blueprint, jsonify, request

auth_bp = Blueprint("auth", __name__)


def init_auth(auth_service):
    @auth_bp.route("/login", methods=["POST"])
    def login():
        payload = request.get_json(silent=True) or {}
        user = auth_service.login(payload.get("username") or "", payload.get("password") or "")
        return jsonify({"message": "登录成功", "user": user})

    @auth_bp.route("/logout", methods=["POST"])
    def logout():
        auth_service.logout()
        return jsonify({"message": "已退出登录"})

    @auth_bp.route("/me", methods=["GET"])
    def me():
        user = auth_service.get_current_user()
        if not user:
            return jsonify({"authenticated": False}), 401
        return jsonify({"authenticated": True, "user": auth_service.public_user(user)})

    return auth_bp
