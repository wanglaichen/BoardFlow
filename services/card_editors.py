"""卡片编辑器注册表：每个第三方库独立一个 app，避免打包冲突。"""

CARD_EDITORS = {
    "canvas": {
        "label": "画布",
        "field": "canvas_data",
        "template": "editors/canvas.html",
        "static_app": "canvas",
        "default_title": "画布",
        "save_message": "画布已保存",
    },
    "mindmap": {
        "label": "思维导图",
        "field": "mindmap_data",
        "template": "editors/mindmap.html",
        "static_app": "mindmap",
        "default_title": "思维导图",
        "save_message": "思维导图已保存",
    },
    "table": {
        "label": "表格",
        "field": "table_data",
        "template": "editors/table.html",
        "static_app": "table",
        "default_title": "表格",
        "save_message": "表格已保存",
    },
}


def get_editor_config(editor_key: str) -> dict:
    config = CARD_EDITORS.get(editor_key)
    if not config:
        raise ValueError(f"未知编辑器类型：{editor_key}")
    return config
