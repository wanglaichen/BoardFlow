import { Editor } from "@tiptap/core";
import Highlight from "@tiptap/extension-highlight";
import Link from "@tiptap/extension-link";
import Placeholder from "@tiptap/extension-placeholder";
import TextAlign from "@tiptap/extension-text-align";
import Underline from "@tiptap/extension-underline";
import { BackgroundColor } from "@tiptap/extension-text-style/background-color";
import { Color } from "@tiptap/extension-text-style/color";
import { TextStyle } from "@tiptap/extension-text-style/text-style";
import StarterKit from "@tiptap/starter-kit";

import "./editor.css";

const EDITOR_HOST_ID = "cardDescriptionEditor";
const TOOLBAR_ID = "cardDescriptionToolbar";

const TEXT_COLORS = [
    { value: "", label: "默认字色" },
    { value: "#1f2328", label: "黑色" },
    { value: "#ef4444", label: "红色" },
    { value: "#f97316", label: "橙色" },
    { value: "#ca8a04", label: "黄色" },
    { value: "#16a34a", label: "绿色" },
    { value: "#2563eb", label: "蓝色" },
    { value: "#9333ea", label: "紫色" },
    { value: "#6b7280", label: "灰色" },
];

const BACKGROUND_COLORS = [
    { value: "", label: "无背景" },
    { value: "#fef08a", label: "黄色高亮" },
    { value: "#bbf7d0", label: "绿色高亮" },
    { value: "#bfdbfe", label: "蓝色高亮" },
    { value: "#fbcfe8", label: "粉色高亮" },
    { value: "#fed7aa", label: "橙色高亮" },
    { value: "#e5e7eb", label: "灰色高亮" },
];

let editor = null;

function escapeHtml(value) {
    return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
}

function isHtmlContent(value) {
    return /<\/?[a-z][\s\S]*>/i.test(String(value || "").trim());
}

function normalizeContent(value) {
    const raw = String(value || "").trim();
    if (!raw) {
        return "";
    }
    if (isHtmlContent(raw)) {
        return raw;
    }
    return raw
        .split(/\r?\n/)
        .map((line) => `<p>${escapeHtml(line)}</p>`)
        .join("");
}

function toolbarButton(label, action, { active = false, title = "" } = {}) {
    return `<button
        class="card-description-toolbar-btn${active ? " is-active" : ""}"
        type="button"
        data-editor-action="${action}"
        title="${escapeHtml(title || label)}"
        aria-label="${escapeHtml(title || label)}"
    >${label}</button>`;
}

function toolbarColorSwatch(color, action, { active = false, title = "" } = {}) {
    const resetClass = color ? "" : " is-reset";
    const style = color ? ` style="--swatch-color:${color}"` : "";
    return `<button
        class="card-description-color-swatch${active ? " is-active" : ""}${resetClass}"
        type="button"
        data-editor-action="${action}"
        data-color-value="${escapeHtml(color)}"
        title="${escapeHtml(title)}"
        aria-label="${escapeHtml(title)}"
        ${style}
    ></button>`;
}

function renderColorGroup(label, colors, action, currentValue) {
    const normalizedCurrent = currentValue || "";
    const swatches = colors
        .map((item) =>
            toolbarColorSwatch(item.value, action, {
                active: item.value === normalizedCurrent,
                title: item.label,
            }),
        )
        .join("");

    return `
        <div class="card-description-toolbar-colors">
            <span class="card-description-toolbar-label">${label}</span>
            <div class="card-description-color-swatches">${swatches}</div>
            <input
                class="card-description-color-input"
                type="color"
                data-editor-action="${action}Picker"
                title="自定义${label}"
                aria-label="自定义${label}"
            >
        </div>
    `;
}

function renderToolbar(activeEditor) {
    const headingValue = activeEditor.isActive("heading", { level: 1 })
        ? "h1"
        : activeEditor.isActive("heading", { level: 2 })
          ? "h2"
          : activeEditor.isActive("heading", { level: 3 })
            ? "h3"
            : "paragraph";
    const textStyle = activeEditor.getAttributes("textStyle");

    return `
        <div class="card-description-toolbar-group">
            ${toolbarButton("↶", "undo", { title: "撤销" })}
            ${toolbarButton("↷", "redo", { title: "重做" })}
        </div>
        <div class="card-description-toolbar-group">
            <select class="card-description-toolbar-select" data-editor-action="heading">
                <option value="paragraph" ${headingValue === "paragraph" ? "selected" : ""}>正文</option>
                <option value="h1" ${headingValue === "h1" ? "selected" : ""}>标题 1</option>
                <option value="h2" ${headingValue === "h2" ? "selected" : ""}>标题 2</option>
                <option value="h3" ${headingValue === "h3" ? "selected" : ""}>标题 3</option>
            </select>
        </div>
        <div class="card-description-toolbar-group">
            ${toolbarButton("B", "bold", { active: activeEditor.isActive("bold"), title: "加粗" })}
            ${toolbarButton("I", "italic", { active: activeEditor.isActive("italic"), title: "斜体" })}
            ${toolbarButton("S", "strike", { active: activeEditor.isActive("strike"), title: "删除线" })}
            ${toolbarButton("U", "underline", { active: activeEditor.isActive("underline"), title: "下划线" })}
        </div>
        <div class="card-description-toolbar-group card-description-toolbar-group-colors">
            ${renderColorGroup("字色", TEXT_COLORS, "textColor", textStyle.color)}
        </div>
        <div class="card-description-toolbar-group card-description-toolbar-group-colors">
            ${renderColorGroup("背景", BACKGROUND_COLORS, "backgroundColor", textStyle.backgroundColor)}
        </div>
        <div class="card-description-toolbar-group">
            ${toolbarButton("•", "bulletList", { active: activeEditor.isActive("bulletList"), title: "无序列表" })}
            ${toolbarButton("1.", "orderedList", { active: activeEditor.isActive("orderedList"), title: "有序列表" })}
            ${toolbarButton("❝", "blockquote", { active: activeEditor.isActive("blockquote"), title: "引用" })}
            ${toolbarButton("🔗", "link", { active: activeEditor.isActive("link"), title: "链接" })}
        </div>
        <div class="card-description-toolbar-group">
            ${toolbarButton("左", "alignLeft", { active: activeEditor.isActive({ textAlign: "left" }), title: "左对齐" })}
            ${toolbarButton("中", "alignCenter", { active: activeEditor.isActive({ textAlign: "center" }), title: "居中" })}
            ${toolbarButton("右", "alignRight", { active: activeEditor.isActive({ textAlign: "right" }), title: "右对齐" })}
        </div>
    `;
}

function applyTextColor(color) {
    if (!editor) {
        return;
    }
    const chain = editor.chain().focus();
    if (!color) {
        chain.unsetColor().run();
        return;
    }
    chain.setColor(color).run();
}

function applyBackgroundColor(color) {
    if (!editor) {
        return;
    }
    const chain = editor.chain().focus();
    if (!color) {
        chain.unsetBackgroundColor().run();
        return;
    }
    chain.setBackgroundColor(color).run();
}

function runToolbarAction(action, value) {
    if (!editor) {
        return;
    }

    const chain = editor.chain().focus();
    switch (action) {
        case "undo":
            chain.undo().run();
            return;
        case "redo":
            chain.redo().run();
            return;
        case "bold":
            chain.toggleBold().run();
            return;
        case "italic":
            chain.toggleItalic().run();
            return;
        case "strike":
            chain.toggleStrike().run();
            return;
        case "underline":
            chain.toggleUnderline().run();
            return;
        case "bulletList":
            chain.toggleBulletList().run();
            return;
        case "orderedList":
            chain.toggleOrderedList().run();
            return;
        case "blockquote":
            chain.toggleBlockquote().run();
            return;
        case "link": {
            const previousUrl = editor.getAttributes("link").href || "";
            const url = window.prompt("输入链接地址", previousUrl);
            if (url === null) {
                return;
            }
            if (!url.trim()) {
                chain.unsetLink().run();
                return;
            }
            chain.setLink({ href: url.trim() }).run();
            return;
        }
        case "alignLeft":
            chain.setTextAlign("left").run();
            return;
        case "alignCenter":
            chain.setTextAlign("center").run();
            return;
        case "alignRight":
            chain.setTextAlign("right").run();
            return;
        case "textColor":
            applyTextColor(value);
            return;
        case "textColorPicker":
            applyTextColor(value);
            return;
        case "backgroundColor":
            applyBackgroundColor(value);
            return;
        case "backgroundColorPicker":
            applyBackgroundColor(value);
            return;
        case "heading":
            if (value === "h1") {
                chain.setHeading({ level: 1 }).run();
            } else if (value === "h2") {
                chain.setHeading({ level: 2 }).run();
            } else if (value === "h3") {
                chain.setHeading({ level: 3 }).run();
            } else {
                chain.setParagraph().run();
            }
            return;
        default:
            return;
    }
}

function bindToolbar() {
    const toolbar = document.getElementById(TOOLBAR_ID);
    if (!toolbar || !editor) {
        return;
    }

    toolbar.innerHTML = renderToolbar(editor);
    toolbar.querySelectorAll("[data-editor-action]").forEach((node) => {
        if (node.tagName === "SELECT") {
            node.addEventListener("change", () => {
                runToolbarAction(node.dataset.editorAction, node.value);
            });
            return;
        }
        if (node.tagName === "INPUT" && node.type === "color") {
            node.addEventListener("input", () => {
                runToolbarAction(node.dataset.editorAction, node.value);
            });
            return;
        }
        if (node.dataset.colorValue !== undefined) {
            node.addEventListener("click", () => {
                runToolbarAction(node.dataset.editorAction, node.dataset.colorValue);
            });
            return;
        }
        node.addEventListener("click", () => {
            runToolbarAction(node.dataset.editorAction);
        });
    });
}

function mount({ content = "" } = {}) {
    destroy();

    const host = document.getElementById(EDITOR_HOST_ID);
    const toolbar = document.getElementById(TOOLBAR_ID);
    if (!host || !toolbar) {
        throw new Error("描述编辑器容器未找到");
    }

    host.classList.add("card-description-editor-host");
    toolbar.classList.add("card-description-toolbar");
    host.innerHTML = "";
    toolbar.innerHTML = "";

    editor = new Editor({
        element: host,
        extensions: [
            StarterKit.configure({
                heading: { levels: [1, 2, 3] },
            }),
            TextStyle,
            Color,
            BackgroundColor,
            Highlight.configure({
                multicolor: true,
            }),
            Underline,
            Link.configure({
                openOnClick: false,
                autolink: true,
            }),
            TextAlign.configure({
                types: ["heading", "paragraph"],
            }),
            Placeholder.configure({
                placeholder: "补充说明、验收标准…",
            }),
        ],
        content: normalizeContent(content),
        autofocus: false,
        onCreate: () => {
            bindToolbar();
        },
        onTransaction: () => {
            bindToolbar();
        },
        editorProps: {
            attributes: {
                class: "card-description-prose",
            },
        },
    });

    if (!editor.editorView?.dom) {
        throw new Error("描述编辑器初始化失败");
    }

    bindToolbar();
}

function destroy() {
    if (editor) {
        editor.destroy();
        editor = null;
    }
    const host = document.getElementById(EDITOR_HOST_ID);
    const toolbar = document.getElementById(TOOLBAR_ID);
    if (host) {
        host.innerHTML = "";
    }
    if (toolbar) {
        toolbar.innerHTML = "";
    }
}

function getHtml() {
    if (!editor) {
        return "";
    }
    const html = editor.getHTML().trim();
    return html === "<p></p>" ? "" : html;
}

function getPlainText() {
    return editor?.getText().trim() || "";
}

window.CardDescriptionEditor = {
    mount,
    destroy,
    getHtml,
    getPlainText,
};
