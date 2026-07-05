import Editor from "@toast-ui/editor";
import Viewer from "@toast-ui/editor/viewer";
import "@toast-ui/editor/dist/toastui-editor.css";
import "@toast-ui/editor/dist/toastui-editor-viewer.css";
import "@toast-ui/editor/dist/theme/toastui-editor-dark.css";
import "@toast-ui/editor/dist/i18n/zh-cn";

import "./editor.css";

const HOST_ID = "cardDescriptionMarkdownEditor";
const VIEW_HOST_ID = "cardDescriptionViewContent";
const PLACEHOLDER_TEXT =
    "支持 GFM Markdown：# 标题、**加粗**、- 列表、```代码块```、> 引用…";

let editor = null;
let viewer = null;

function isEmptyMarkdownBlock(block) {
    if (!block) {
        return true;
    }
    const text = block.textContent?.replace(/\u200b/g, "").trim() ?? "";
    return !text;
}

function normalizeEmptyMarkdownEditor(host) {
    if (!host) {
        return;
    }

    editor?.blur?.();

    const root = host.querySelector(".ProseMirror");
    if (!root) {
        return;
    }

    root.querySelectorAll(':scope > div[class*="line-background"]').forEach((block) => {
        if (isEmptyMarkdownBlock(block)) {
            block.className = "";
        }
    });

    root.querySelectorAll(".placeholder").forEach((node) => {
        node.style.pointerEvents = "none";
    });
}

function mount({ content = "" } = {}) {
    destroyEditor();

    const host = document.getElementById(HOST_ID);
    if (!host) {
        throw new Error("Markdown 编辑器容器未找到");
    }

    host.innerHTML = "";
    host.classList.add("card-description-markdown-host");

    editor = new Editor({
        el: host,
        height: "320px",
        initialEditType: "markdown",
        previewStyle: "vertical",
        theme: "dark",
        language: "zh-CN",
        initialValue: String(content || ""),
        placeholder: PLACEHOLDER_TEXT,
        usageStatistics: false,
        hideModeSwitch: true,
        autofocus: false,
        toolbarItems: [
            ["heading", "bold", "italic", "strike"],
            ["hr", "quote"],
            ["ul", "ol", "task", "indent", "outdent"],
            ["table", "link", "code", "codeblock"],
        ],
        events: {
            load: () => {
                requestAnimationFrame(() => normalizeEmptyMarkdownEditor(host));
            },
            change: () => {
                if (!editor?.getMarkdown?.().trim()) {
                    normalizeEmptyMarkdownEditor(host);
                }
            },
        },
    });

    requestAnimationFrame(() => normalizeEmptyMarkdownEditor(host));
}

function mountViewer({ content = "" } = {}) {
    destroyViewer();

    const host = document.getElementById(VIEW_HOST_ID);
    if (!host) {
        throw new Error("Markdown 预览容器未找到");
    }

    host.innerHTML = "";
    host.classList.add("card-description-markdown-view");

    viewer = new Viewer({
        el: host,
        initialValue: String(content || ""),
        theme: "dark",
        language: "zh-CN",
        usageStatistics: false,
    });
}

function destroyEditor() {
    if (editor) {
        editor.destroy();
        editor = null;
    }
    const host = document.getElementById(HOST_ID);
    if (host) {
        host.innerHTML = "";
        host.classList.remove("card-description-markdown-host");
    }
}

function destroyViewer() {
    if (viewer) {
        viewer.destroy();
        viewer = null;
    }
    const host = document.getElementById(VIEW_HOST_ID);
    if (host) {
        host.innerHTML = "";
        host.classList.remove("card-description-markdown-view");
    }
}

function destroy() {
    destroyEditor();
    destroyViewer();
}

function getMarkdown() {
    if (!editor) {
        return "";
    }
    return editor.getMarkdown().trim();
}

function setMarkdown(content) {
    if (!editor) {
        return;
    }
    editor.setMarkdown(String(content || ""), false);
    requestAnimationFrame(() => normalizeEmptyMarkdownEditor(document.getElementById(HOST_ID)));
}

window.CardMarkdownEditor = {
    mount,
    mountViewer,
    destroy,
    destroyEditor,
    destroyViewer,
    getMarkdown,
    setMarkdown,
};
