/** 卡片扩展视图配置：每个编辑器独立打包，避免第三方库冲突。 */
const CARD_VIEW_ACTIONS = [
    { id: "canvas", label: "画布", icon: "canvas", dataKey: "canvas_data", enabled: true },
    { id: "mindmap", label: "思维导图", icon: "mindmap", dataKey: "mindmap_data", enabled: true },
    { id: "table", label: "表格", icon: "table", dataKey: "table_data", enabled: true },
];

const CARD_VIEW_ICONS = {
    canvas: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 15l3-3 2 2 5-5"/><circle cx="8.5" cy="8.5" r="1.5" fill="currentColor" stroke="none"/></svg>`,
    mindmap: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="2.5"/><path d="M12 9.5V5M12 19v-4.5M14.5 12H19M5 12h4.5M14.1 9.9l3.2-3.2M6.7 17.3l3.2-3.2M14.1 14.1l3.2 3.2M6.7 6.7l3.2 3.2"/></svg>`,
    table: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M9 5v14M15 5v14"/></svg>`,
};

function hasCanvasData(value) {
    if (value == null) {
        return false;
    }
    if (typeof value === "object") {
        return Object.keys(value).length > 0;
    }
    return Boolean(value);
}

function hasMindmapData(value) {
    if (!value || typeof value !== "object") {
        return false;
    }
    const node = value.nodeData;
    if (node && Array.isArray(node.children) && node.children.length > 0) {
        return true;
    }
    if (Array.isArray(value.arrows) && value.arrows.length > 0) {
        return true;
    }
    if (Array.isArray(value.summaries) && value.summaries.length > 0) {
        return true;
    }
    return false;
}

function hasTableData(value) {
    if (!Array.isArray(value) || !value.length) {
        return false;
    }
    return value.some((sheet) => Array.isArray(sheet.celldata) && sheet.celldata.length > 0);
}

function cardHasViewData(card, action) {
    if (action.id === "canvas") {
        return hasCanvasData(card[action.dataKey]);
    }
    if (action.id === "mindmap") {
        return hasMindmapData(card[action.dataKey]);
    }
    if (action.id === "table") {
        return hasTableData(card[action.dataKey]);
    }
    const value = card[action.dataKey];
    if (value == null) {
        return false;
    }
    if (typeof value === "object") {
        return Object.keys(value).length > 0;
    }
    return Boolean(value);
}

function renderCardViewActionIcon(icon) {
    return CARD_VIEW_ICONS[icon] || CARD_VIEW_ICONS.canvas;
}

function getCardViewActionsForMode(card, viewMode = "kanban") {
    const actions = CARD_VIEW_ACTIONS.filter((action) => action.enabled && cardHasViewData(card, action));
    if (viewMode === "kanban") {
        return actions;
    }
    if (viewMode === "canvas" || viewMode === "mindmap" || viewMode === "table") {
        return actions.filter((action) => action.id === viewMode);
    }
    return actions;
}

function renderCardViewActions(card, viewMode = "kanban") {
    const actions = getCardViewActionsForMode(card, viewMode);
    if (!actions.length) {
        return "";
    }

    return `
        <div class="card-view-actions">
            ${actions
                .map((action) => {
                    const locked = isCardEditorLocked(card.id, action.id);
                    const holder = cardEditorLockHolder(card.id, action.id);
                    const lockTitle = locked
                        ? `${holder?.display_name || "其他用户"} 正在编辑`
                        : escapeHtml(action.label);
                    return `
                <button
                    class="card-view-action-btn has-data${locked ? " is-locked" : ""}"
                    type="button"
                    data-card-view-action="${action.id}"
                    title="${escapeHtml(lockTitle)}"
                    aria-label="${escapeHtml(lockTitle)}"
                >${renderCardViewActionIcon(action.icon)}${locked ? '<span class="card-view-lock-dot" aria-hidden="true"></span>' : ""}</button>
            `;
                })
                .join("")}
        </div>
    `;
}

async function openCardEditor(cardId, editorKey) {
    if (!state.currentBoardId) {
        return;
    }
    const action = CARD_VIEW_ACTIONS.find((item) => item.id === editorKey);
    const acquired = await acquireEditorLockBeforeOpen(
        state.currentBoardId,
        cardId,
        editorKey,
        action?.label || "编辑器"
    );
    if (!acquired) {
        return;
    }
    saveBoardViewPreference(state.currentBoardId, state.currentBoardView || editorKey);
    const from = encodeURIComponent(location.hash || `#/board/${state.currentBoardId}`);
    let href = `/board/${state.currentBoardId}/card/${cardId}/${editorKey}?from=${from}`;
    if (state.currentBoardAccess?.shared) {
        href += `&owner_tenant_type=${encodeURIComponent(state.currentBoardAccess.owner_tenant_type)}`;
        href += `&owner_tenant_id=${encodeURIComponent(state.currentBoardAccess.owner_tenant_id)}`;
    }
    window.location.href = href;
}

function openCardCanvas(cardId) {
    openCardEditor(cardId, "canvas");
}

function openCardMindmap(cardId) {
    openCardEditor(cardId, "mindmap");
}

function openCardTable(cardId) {
    openCardEditor(cardId, "table");
}

function handleCardViewAction(actionId, cardId) {
    const action = CARD_VIEW_ACTIONS.find((item) => item.id === actionId && item.enabled);
    if (!action) {
        showError("该视图即将支持");
        return;
    }
    openCardEditor(cardId, actionId).catch((error) => showError(error.message || "无法打开编辑器"));
}

function isEditorBoardView(view = state.currentBoardView) {
    return view === "canvas" || view === "mindmap" || view === "table";
}

function openCardForBoardView(cardId, view = state.currentBoardView) {
    if (view === "canvas") {
        openCardCanvas(cardId);
        return;
    }
    if (view === "mindmap") {
        openCardMindmap(cardId);
        return;
    }
    if (view === "table") {
        openCardTable(cardId);
        return;
    }
    openCardModal(cardId);
}
