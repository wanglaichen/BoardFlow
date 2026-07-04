const state = {
    settings: { card_types: [] },
    boards: [],
    currentBoard: null,
    currentBoardId: null,
    currentBoardView: "kanban",
    editingCard: null,
    editingBoardId: null,
    sortables: [],
    editingChecklistIndex: null,
    checklistEditBackup: "",
    boardHub: {
        scope: "personal",
        orgName: "",
        sortBy: "custom",
    },
    boardHubGroups: {
        mine: true,
        projects: true,
    },
};

const PERSONAL_BOARD_ORGANIZATION = "个人看板";
const BOARD_HUB_STAR_STORAGE_KEY = "boardflow:starred-boards";

function normalizeBoardOrganization(name) {
    const value = (name || "").trim();
    return value || PERSONAL_BOARD_ORGANIZATION;
}

function formatBoardOrganization(name) {
    return normalizeBoardOrganization(name);
}

function getBoardOrgElements() {
    return {
        input: document.getElementById("boardOrgInput"),
        options: document.getElementById("boardOrgOptions"),
    };
}

const appView = document.getElementById("appView");
const errorBox = document.getElementById("errorBox");
const successBox = document.getElementById("successBox");
const cardModalEl = document.getElementById("cardModal");
const boardFormModalEl = document.getElementById("boardFormModal");
const quickCreateModalEl = document.getElementById("quickCreateModal");
const confirmDeleteModalEl = document.getElementById("confirmDeleteModal");
const cardModal = new bootstrap.Modal(cardModalEl);
const boardFormModal = new bootstrap.Modal(boardFormModalEl);
const quickCreateModal = new bootstrap.Modal(quickCreateModalEl);
const confirmDeleteModal = new bootstrap.Modal(confirmDeleteModalEl);
const quickCreateTitleEl = document.getElementById("quickCreateTitle");
const quickCreateInput = document.getElementById("quickCreateInput");
const confirmDeleteTitleEl = document.getElementById("confirmDeleteTitle");
const confirmDeleteMessageEl = document.getElementById("confirmDeleteMessage");
let quickCreateSubmitHandler = null;
let confirmDeleteSubmitHandler = null;
let pendingDescriptionContent = null;
let pendingDescriptionMode = "richtext";

const cardDescriptionModeSelect = document.getElementById("cardDescriptionModeSelect");
const cardDescriptionWrap = document.getElementById("cardDescriptionWrap");
const cardDescriptionRichtextPane = document.getElementById("cardDescriptionRichtextPane");
const cardDescriptionMarkdownPane = document.getElementById("cardDescriptionMarkdownPane");
const cardDescriptionMarkdownInput = document.getElementById("cardDescriptionMarkdownInput");
const cardDescriptionMarkdownPreview = document.getElementById("cardDescriptionMarkdownPreview");

const cardTypeSelect = document.getElementById("cardTypeSelect");
const cardTitleInput = document.getElementById("cardTitleInput");
const checklistContainer = document.getElementById("checklistContainer");
const commentsContainer = document.getElementById("commentsContainer");
const commentInput = document.getElementById("commentInput");
const globalSearchInput = document.getElementById("globalSearchInput");
const searchResultsPanel = document.getElementById("searchResults");
const boardStatusSelect = document.getElementById("boardStatusSelect");

document.getElementById("saveCardBtn").addEventListener("click", saveCard);
document.getElementById("deleteCardBtn").addEventListener("click", deleteCurrentCard);
document.getElementById("submitCommentBtn").addEventListener("click", submitComment);
document.getElementById("addChecklistItemBtn").addEventListener("click", addChecklistItem);
document.getElementById("saveBoardFormBtn").addEventListener("click", saveBoardForm);
document.getElementById("createBoardNavBtn").addEventListener("click", () => {
    openBoardForm().catch((error) => showError(error.message || "打开看板表单失败"));
});
document.getElementById("quickCreateConfirmBtn").addEventListener("click", submitQuickCreate);
document.getElementById("confirmDeleteSubmitBtn").addEventListener("click", submitConfirmDelete);
quickCreateInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        submitQuickCreate();
    }
});
quickCreateModalEl.addEventListener("shown.bs.modal", () => {
    quickCreateInput.focus();
    quickCreateInput.select();
});
function isHtmlDescription(value) {
    return /<\/?[a-z][\s\S]*>/i.test(String(value || "").trim());
}

function resolveCardDescriptionMode(card) {
    const mode = card?.description_data?.mode;
    if (mode === "markdown" || mode === "richtext") {
        return mode;
    }
    if (isHtmlDescription(card?.description)) {
        return "richtext";
    }
    return "richtext";
}

function applyDescriptionModeUI(mode) {
    const isMarkdown = mode === "markdown";
    cardDescriptionWrap?.classList.toggle("is-markdown-mode", isMarkdown);
    cardDescriptionRichtextPane?.classList.toggle("is-hidden", isMarkdown);
    cardDescriptionMarkdownPane?.classList.toggle("is-hidden", !isMarkdown);
    if (cardDescriptionMarkdownPane) {
        cardDescriptionMarkdownPane.hidden = !isMarkdown;
    }
}

function renderMarkdownInline(text) {
    let output = escapeHtml(text);
    output = output.replace(/`([^`]+)`/g, "<code>$1</code>");
    output = output.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    output = output.replace(/\*(.+?)\*/g, "<em>$1</em>");
    output = output.replace(
        /\[([^\]]+)\]\(([^)]+)\)/g,
        (_match, label, href) =>
            `<a href="${escapeHtml(href)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    );
    return output;
}

function renderMarkdownToHtml(source) {
    const lines = String(source || "").split(/\r?\n/);
    const html = [];
    let inCode = false;
    let codeLines = [];
    let listType = null;
    const listItems = [];

    function flushList() {
        if (!listItems.length) {
            return;
        }
        html.push(listType === "ol" ? "<ol>" : "<ul>");
        listItems.forEach((item) => html.push(`<li>${item}</li>`));
        html.push(listType === "ol" ? "</ol>" : "</ul>");
        listItems.length = 0;
        listType = null;
    }

    for (const line of lines) {
        const fence = line.trim();
        if (fence.startsWith("```")) {
            flushList();
            if (inCode) {
                html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
                codeLines = [];
                inCode = false;
            } else {
                inCode = true;
            }
            continue;
        }
        if (inCode) {
            codeLines.push(line);
            continue;
        }

        const trimmed = line.trim();
        if (!trimmed) {
            flushList();
            continue;
        }
        if (/^#{1,3}\s+/.test(trimmed)) {
            flushList();
            const level = trimmed.match(/^#+/)[0].length;
            const text = trimmed.replace(/^#+\s+/, "");
            html.push(`<h${level}>${renderMarkdownInline(text)}</h${level}>`);
            continue;
        }
        if (/^>\s+/.test(trimmed)) {
            flushList();
            html.push(`<blockquote><p>${renderMarkdownInline(trimmed.replace(/^>\s+/, ""))}</p></blockquote>`);
            continue;
        }
        if (/^[-*]\s+/.test(trimmed)) {
            if (listType && listType !== "ul") {
                flushList();
            }
            listType = "ul";
            listItems.push(renderMarkdownInline(trimmed.replace(/^[-*]\s+/, "")));
            continue;
        }
        if (/^\d+\.\s+/.test(trimmed)) {
            if (listType && listType !== "ol") {
                flushList();
            }
            listType = "ol";
            listItems.push(renderMarkdownInline(trimmed.replace(/^\d+\.\s+/, "")));
            continue;
        }
        flushList();
        html.push(`<p>${renderMarkdownInline(trimmed)}</p>`);
    }

    flushList();
    if (inCode && codeLines.length) {
        html.push(`<pre><code>${escapeHtml(codeLines.join("\n"))}</code></pre>`);
    }
    return html.join("");
}

function syncMarkdownPreview() {
    if (!cardDescriptionMarkdownPreview) {
        return;
    }
    const source = cardDescriptionMarkdownInput?.value || "";
    cardDescriptionMarkdownPreview.innerHTML = source.trim()
        ? renderMarkdownToHtml(source)
        : '<p class="card-description-markdown-empty">预览将显示在这里</p>';
}

function switchDescriptionMode(nextMode) {
    const mode = nextMode === "markdown" ? "markdown" : "richtext";
    const currentMode = cardDescriptionModeSelect?.value || pendingDescriptionMode || "richtext";
    if (mode !== currentMode) {
        if (mode === "markdown") {
            let plainText = "";
            if (typeof CardDescriptionEditor !== "undefined") {
                plainText = CardDescriptionEditor.getPlainText?.() || "";
            }
            if (typeof CardDescriptionEditor !== "undefined") {
                CardDescriptionEditor.destroy();
            }
            if (cardDescriptionMarkdownInput) {
                cardDescriptionMarkdownInput.value = plainText;
            }
            syncMarkdownPreview();
        } else {
            pendingDescriptionContent = cardDescriptionMarkdownInput?.value || "";
            mountCardDescriptionEditor();
        }
    }
    pendingDescriptionMode = mode;
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = mode;
    }
    applyDescriptionModeUI(mode);
}

function collectDescriptionPayload() {
    const mode = cardDescriptionModeSelect?.value || pendingDescriptionMode || "richtext";
    if (mode === "markdown") {
        return {
            description: cardDescriptionMarkdownInput?.value || "",
            description_data: { mode: "markdown" },
        };
    }
    return {
        description: typeof CardDescriptionEditor !== "undefined" ? CardDescriptionEditor.getHtml() : "",
        description_data: { mode: "richtext" },
    };
}

function mountCardDescriptionEditor() {
    if (typeof CardDescriptionEditor === "undefined") {
        showError("描述编辑器脚本未加载，请 Ctrl+F5 强刷后重试");
        return;
    }
    try {
        CardDescriptionEditor.mount({ content: pendingDescriptionContent ?? "" });
    } catch (error) {
        showError(error.message || "描述编辑器初始化失败");
    }
}

cardModalEl.addEventListener("shown.bs.modal", () => {
    if (!state.editingCard) {
        return;
    }
    if ((cardDescriptionModeSelect?.value || pendingDescriptionMode) === "richtext") {
        mountCardDescriptionEditor();
    }
});
cardModalEl.addEventListener("hidden.bs.modal", () => {
    if (typeof CardDescriptionEditor !== "undefined") {
        CardDescriptionEditor.destroy();
    }
    pendingDescriptionContent = null;
    pendingDescriptionMode = "richtext";
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = "richtext";
    }
    if (cardDescriptionMarkdownInput) {
        cardDescriptionMarkdownInput.value = "";
    }
    syncMarkdownPreview();
    applyDescriptionModeUI("richtext");
});
cardDescriptionModeSelect?.addEventListener("change", () => {
    switchDescriptionMode(cardDescriptionModeSelect.value);
});
cardDescriptionMarkdownInput?.addEventListener("input", syncMarkdownPreview);
[cardModalEl, boardFormModalEl, quickCreateModalEl, confirmDeleteModalEl].forEach((modalEl) => {
    modalEl.addEventListener("hidden.bs.modal", cleanupModalOverlay);
});
confirmDeleteModalEl.addEventListener("hidden.bs.modal", () => {
    confirmDeleteSubmitHandler = null;
});
appView.addEventListener("click", handleBoardPageClick);
globalSearchInput.addEventListener("input", debounce(() => performSearch(globalSearchInput.value.trim()), 250));
globalSearchInput.addEventListener("keydown", handleSearchKeydown);

window.addEventListener("hashchange", renderRoute);
window.addEventListener("click", (event) => {
    if (!event.target.closest(".search-box")) {
        closeSearchPanel();
    }
    if (!event.target.closest(".board-status-dropdown")) {
        document.querySelectorAll(".board-status-menu.show").forEach((node) => node.classList.remove("show"));
    }
    if (!event.target.closest(".board-org-dropdown")) {
        document.querySelectorAll(".board-org-menu.show").forEach((node) => node.classList.remove("show"));
    }
    if (!event.target.closest(".list-menu-dropdown")) {
        closeAllListMenus();
    }
});

init();

async function init() {
    cleanupModalOverlay();
    try {
        await loadSettings();
        await loadBoards();
        renderRoute();
    } catch (error) {
        showError(error.message || "初始化失败");
    }
}

function renderRoute() {
    destroySortables();
    const hash = location.hash || "#/home/personal";
    const boardMatch = hash.match(/^#\/board\/(\d+)(?:\/card\/([^/]+))?/);
    if (boardMatch) {
        openBoard(boardMatch[1], boardMatch[2] || null);
        return;
    }
    if (hash === "#/settings" || hash.startsWith("#/settings/")) {
        if (hash === "#/settings") {
            history.replaceState(null, "", "#/settings/statuses");
        }
        renderSettingsPage(resolveSettingsTab(location.hash));
        return;
    }
    if (hash.startsWith("#/home")) {
        applyBoardHubRoute(hash);
        renderBoardList();
        return;
    }
    applyBoardHubRoute("#/home/personal");
    renderBoardList();
}

function applyBoardHubRoute(hash) {
    const normalized = hash.split("?")[0];
    const orgMatch = normalized.match(/^#\/home\/org\/(.+)$/);

    if (orgMatch) {
        state.boardHub.scope = "org";
        state.boardHub.orgName = decodeURIComponent(orgMatch[1]);
        return;
    }
    if (normalized === "#/home/workbench") {
        state.boardHub.scope = "workbench";
        state.boardHub.orgName = "";
        return;
    }
    if (normalized === "#/home/mindmap") {
        history.replaceState(null, "", "#/home/personal");
    }
    if (normalized === "#/home/starred") {
        state.boardHub.scope = "starred";
        state.boardHub.orgName = "";
        return;
    }
    if (normalized === "#/home/list" || normalized === "#/home" || normalized === "#/home/") {
        history.replaceState(null, "", "#/home/personal");
    }
    state.boardHub.scope = "personal";
    state.boardHub.orgName = "";
}

function buildBoardHubHref(scope, orgName = "") {
    if (scope === "org" && orgName) {
        return `#/home/org/${encodeURIComponent(orgName)}`;
    }
    if (scope === "workbench") {
        return "#/home/workbench";
    }
    if (scope === "starred") {
        return "#/home/starred";
    }
    return "#/home/personal";
}

function getBoardHubBackHref() {
    return buildBoardHubHref(state.boardHub.scope, state.boardHub.orgName);
}

function getBoardHubTitle(hub = state.boardHub) {
    if (hub.scope === "workbench") {
        return "工作台";
    }
    if (hub.scope === "starred") {
        return "星标看板";
    }
    if (hub.scope === "org") {
        return hub.orgName || "项目看板";
    }
    return PERSONAL_BOARD_ORGANIZATION;
}

function getDefaultOrgForHub() {
    if (state.boardHub.scope === "org" && state.boardHub.orgName) {
        return state.boardHub.orgName;
    }
    return PERSONAL_BOARD_ORGANIZATION;
}

function getStarredBoardIds() {
    try {
        const raw = localStorage.getItem(BOARD_HUB_STAR_STORAGE_KEY);
        const parsed = raw ? JSON.parse(raw) : [];
        return Array.isArray(parsed) ? parsed.map(String) : [];
    } catch {
        return [];
    }
}

function isBoardStarred(boardId) {
    return getStarredBoardIds().includes(String(boardId));
}

function toggleBoardStar(boardId) {
    const key = String(boardId);
    const ids = getStarredBoardIds();
    const next = ids.includes(key) ? ids.filter((item) => item !== key) : [...ids, key];
    localStorage.setItem(BOARD_HUB_STAR_STORAGE_KEY, JSON.stringify(next));
}

function filterBoardsForHub(boards, hub = state.boardHub) {
    if (hub.scope === "workbench") {
        return boards.slice();
    }
    if (hub.scope === "starred") {
        const starred = new Set(getStarredBoardIds());
        return boards.filter((board) => starred.has(String(board.id)));
    }
    if (hub.scope === "org") {
        const orgName = normalizeBoardOrganization(hub.orgName);
        return boards.filter((board) => normalizeBoardOrganization(board.organization) === orgName);
    }
    return boards.filter(
        (board) => normalizeBoardOrganization(board.organization) === PERSONAL_BOARD_ORGANIZATION
    );
}

function sortBoardsForHub(boards, sortBy = state.boardHub.sortBy) {
    const items = boards.slice();
    const starred = new Set(getStarredBoardIds());

    if (sortBy === "name") {
        return items.sort((left, right) => (left.title || "").localeCompare(right.title || "", "zh-CN"));
    }
    if (sortBy === "time") {
        return items.sort(
            (left, right) =>
                new Date(right.updated_at || right.created_at || 0).getTime() -
                new Date(left.updated_at || left.created_at || 0).getTime()
        );
    }
    return items.sort((left, right) => {
        const leftStar = starred.has(String(left.id));
        const rightStar = starred.has(String(right.id));
        if (leftStar !== rightStar) {
            return leftStar ? -1 : 1;
        }
        return (left.title || "").localeCompare(right.title || "", "zh-CN");
    });
}

async function loadSettings() {
    state.settings = await api("/api/settings");
    cardTypeSelect.innerHTML = (state.settings.card_types || [])
        .map((item) => `<option value="${item.id}">${item.label}</option>`)
        .join("");
    applyEditableFontSettings();
}

function getBoardStatuses() {
    return state.settings.board_statuses || state.currentBoard?.settings?.board_statuses || [];
}

function getOrganizations() {
    return state.settings.organizations || state.currentBoard?.settings?.organizations || [];
}

function resolveBoardStatus(board) {
    const statuses = getBoardStatuses();
    const statusId = board?.status_id || statuses.find((item) => item.label === board?.status)?.id || "unset";
    return (
        statuses.find((item) => item.id === statusId) || {
            id: "unset",
            label: board?.status || "未设状态",
            color: "#6b7280",
            icon: "none",
        }
    );
}

function renderStatusIcon(status) {
    if (!status || status.icon === "none") {
        return "";
    }
    if (status.icon === "circle") {
        return `<span class="status-icon status-icon-circle" style="color:${status.color};border-color:${status.color}"></span>`;
    }
    if (status.icon === "dot") {
        return `<span class="status-icon status-icon-dot" style="color:${status.color};border-color:${status.color}"><span style="background:${status.color}"></span></span>`;
    }
    if (status.icon === "check") {
        return `<span class="status-icon status-icon-check" style="background:${status.color}">✓</span>`;
    }
    return "";
}

function renderBoardTitleMeta(board) {
    const createdAt = formatDateTime(board.created_at) || "—";
    const updatedAt = formatDateTime(board.updated_at) || "—";

    return `
        <span class="board-meta-item">
            <span class="board-meta-label">所属组织</span>
            <span class="board-meta-value">${renderBoardOrgBadge(board, { interactive: true })}</span>
        </span>
        <span class="board-meta-item">
            <span class="board-meta-label">状态</span>
            <span class="board-meta-value">${renderBoardStatusBadge(board, { interactive: true })}</span>
        </span>
        <span class="board-meta-item">
            <span class="board-meta-label">创建时间</span>
            <span class="board-meta-value">${escapeHtml(createdAt)}</span>
        </span>
        <span class="board-meta-item">
            <span class="board-meta-label">更新时间</span>
            <span class="board-meta-value">${escapeHtml(updatedAt)}</span>
        </span>
    `;
}

function renderBoardStatusBadge(board, { interactive = false } = {}) {
    const status = resolveBoardStatus(board);
    const statuses = getBoardStatuses();
    const currentId = status.id;

    if (!interactive) {
        return `<span class="board-status-pill">${renderStatusIcon(status)}${escapeHtml(status.label)}</span>`;
    }

    return `
        <div class="board-status-dropdown">
            <button class="board-status-badge" id="boardStatusBtn" type="button">
                ${renderStatusIcon(status)}
                <span>${escapeHtml(status.label)}</span>
            </button>
            <div class="board-status-menu" id="boardStatusMenu">
                ${statuses
                    .map(
                        (item) => `
                    <button
                        class="board-status-option ${item.id === currentId ? "active" : ""}"
                        data-status-id="${item.id}"
                        type="button"
                    >
                        ${renderStatusIcon(item)}
                        <span>${escapeHtml(item.label)}</span>
                        ${item.id === currentId ? '<span class="status-check">✓</span>' : ""}
                    </button>
                `
                    )
                    .join("")}
            </div>
        </div>
    `;
}

function getBoardOrganizationOptions(currentName = "") {
    const seen = new Set();
    const options = [];

    const add = (name) => {
        const value = normalizeBoardOrganization(name);
        if (seen.has(value)) {
            return;
        }
        seen.add(value);
        options.push(value);
    };

    add(PERSONAL_BOARD_ORGANIZATION);
    getOrganizations().forEach((item) => add(item.name));
    add(currentName);
    return options;
}

function renderBoardOrgBadge(board, { interactive = false } = {}) {
    const organization = formatBoardOrganization(board.organization);

    if (!interactive) {
        return `<span class="board-org-pill">${escapeHtml(organization)}</span>`;
    }

    const options = getBoardOrganizationOptions(board.organization);

    return `
        <div class="board-org-dropdown">
            <button class="board-org-badge" id="boardOrgBtn" type="button" title="点击切换所属组织">
                <span>${escapeHtml(organization)}</span>
                <span class="board-org-caret">▾</span>
            </button>
            <div class="board-org-menu" id="boardOrgMenu">
                ${options
                    .map(
                        (name) => `
                    <button
                        class="board-org-option ${name === organization ? "active" : ""}"
                        data-org-name="${escapeHtml(name)}"
                        type="button"
                    >
                        <span>${escapeHtml(name)}</span>
                        ${name === organization ? '<span class="status-check">✓</span>' : ""}
                    </button>
                `
                    )
                    .join("")}
                <button class="board-org-option board-org-option-custom" data-action="custom-org" type="button">
                    <span>输入其他组织...</span>
                </button>
            </div>
        </div>
    `;
}

function populateBoardStatusSelect(selectedId = "not_started") {
    const statuses = getBoardStatuses();
    boardStatusSelect.innerHTML = statuses
        .map((item) => `<option value="${item.id}">${item.label}</option>`)
        .join("");
    boardStatusSelect.value = selectedId;
}

function populateBoardOrgInput(selectedName = PERSONAL_BOARD_ORGANIZATION) {
    const { input: orgInput, options: orgOptions } = getBoardOrgElements();
    if (!orgInput) {
        throw new Error("看板表单组件缺失，请刷新页面后重试");
    }

    const organizations = getOrganizations();
    const current = normalizeBoardOrganization(selectedName);
    const seen = new Set([PERSONAL_BOARD_ORGANIZATION]);
    const options = [`<option value="${escapeHtml(PERSONAL_BOARD_ORGANIZATION)}"></option>`];

    organizations.forEach((item) => {
        const name = (item.name || "").trim();
        if (!name || seen.has(name)) {
            return;
        }
        seen.add(name);
        options.push(`<option value="${escapeHtml(name)}"></option>`);
    });

    if (!seen.has(current)) {
        options.push(`<option value="${escapeHtml(current)}"></option>`);
    }

    if (orgOptions) {
        orgOptions.innerHTML = options.join("");
    }
    orgInput.value = current;
}

function closeBoardMetaMenus(exceptMenu = null) {
    document.querySelectorAll(".board-status-menu.show, .board-org-menu.show").forEach((node) => {
        if (node !== exceptMenu) {
            node.classList.remove("show");
        }
    });
}

function bindBoardStatusDropdown() {
    const button = document.getElementById("boardStatusBtn");
    const menu = document.getElementById("boardStatusMenu");
    if (!button || !menu) {
        return;
    }

    button.addEventListener("click", (event) => {
        event.stopPropagation();
        const willShow = !menu.classList.contains("show");
        closeBoardMetaMenus();
        if (willShow) {
            menu.classList.add("show");
        }
    });

    menu.querySelectorAll("[data-status-id]").forEach((node) => {
        node.addEventListener("click", async (event) => {
            event.stopPropagation();
            await updateBoardStatus(node.dataset.statusId);
            menu.classList.remove("show");
        });
    });
}

function bindBoardOrgDropdown() {
    const button = document.getElementById("boardOrgBtn");
    const menu = document.getElementById("boardOrgMenu");
    if (!button || !menu) {
        return;
    }

    button.addEventListener("click", (event) => {
        event.stopPropagation();
        const willShow = !menu.classList.contains("show");
        closeBoardMetaMenus();
        if (willShow) {
            menu.classList.add("show");
        }
    });

    menu.querySelectorAll("[data-org-name]").forEach((node) => {
        node.addEventListener("click", async (event) => {
            event.stopPropagation();
            await updateBoardOrganization(node.dataset.orgName);
            menu.classList.remove("show");
        });
    });

    menu.querySelector("[data-action='custom-org']")?.addEventListener("click", (event) => {
        event.stopPropagation();
        menu.classList.remove("show");
        promptCustomBoardOrganization(state.currentBoard?.board?.organization);
    });
}

async function updateBoardOrganization(organizationName) {
    if (!state.currentBoardId) {
        return;
    }
    const organization = normalizeBoardOrganization(organizationName);
    const result = await api(`/api/boards/${state.currentBoardId}`, {
        method: "PATCH",
        body: JSON.stringify({ organization }),
    });
    state.currentBoard.board = result.item;
    await loadBoards();
    await openBoard(state.currentBoardId);
    showSuccess("所属组织已更新");
}

function promptCustomBoardOrganization(currentName = "") {
    openQuickCreateDialog({
        title: "修改所属组织",
        placeholder: "输入组织名称，例如：壮游科技",
        defaultValue: formatBoardOrganization(currentName),
        onSubmit: async (name) => {
            await updateBoardOrganization(name);
        },
    });
}

async function updateBoardStatus(statusId) {
    if (!state.currentBoardId) {
        return;
    }
    const result = await api(`/api/boards/${state.currentBoardId}`, {
        method: "PATCH",
        body: JSON.stringify({ status_id: statusId }),
    });
    state.currentBoard.board = result.item;
    await loadBoards();
    renderBoardPage();
    showSuccess("看板状态已更新");
}

function findBoardById(boardId) {
    const fromList = state.boards.find((item) => String(item.id) === String(boardId));
    if (fromList) {
        return fromList;
    }
    if (state.currentBoard?.board && String(state.currentBoard.board.id) === String(boardId)) {
        return state.currentBoard.board;
    }
    return null;
}

const STATUS_ICON_OPTIONS = [
    { id: "circle", label: "空心圆" },
    { id: "dot", label: "实心点" },
    { id: "check", label: "勾选" },
    { id: "none", label: "无图标" },
];

const EDITABLE_FONT_FAMILIES = [
    { id: "microsoft-yahei", label: "微软雅黑", stack: '"Microsoft YaHei", "PingFang SC", sans-serif' },
    { id: "simsun", label: "宋体", stack: 'SimSun, "Songti SC", serif' },
    { id: "simhei", label: "黑体", stack: 'SimHei, "Heiti SC", sans-serif' },
    { id: "kaiti", label: "楷体", stack: 'KaiTi, "Kaiti SC", serif' },
    { id: "pingfang-sc", label: "苹方", stack: '"PingFang SC", "Microsoft YaHei", sans-serif' },
    { id: "noto-sans-sc", label: "思源黑体", stack: '"Noto Sans SC", "Microsoft YaHei", sans-serif' },
    { id: "arial", label: "Arial", stack: 'Arial, Helvetica, sans-serif' },
    { id: "system-ui", label: "系统默认", stack: 'system-ui, -apple-system, "Segoe UI", sans-serif' },
];

const EDITABLE_FONT_STYLES = [
    { id: "normal", label: "正体" },
    { id: "italic", label: "斜体" },
];

const EDITABLE_FONT_WEIGHTS = [
    { id: "400", label: "常规 (400)" },
    { id: "500", label: "中等 (500)" },
    { id: "600", label: "半粗 (600)" },
    { id: "700", label: "加粗 (700)" },
];

const DEFAULT_EDITABLE_FONTS = {
    board_title: { family: "microsoft-yahei", style: "normal", weight: "400", size: "22", color: "#e8eaed" },
    list_title: { family: "microsoft-yahei", style: "normal", weight: "600", size: "15", color: "#e8eaed" },
    card_title_board: { family: "microsoft-yahei", style: "normal", weight: "400", size: "14", color: "#e8eaed" },
    card_title_modal: { family: "microsoft-yahei", style: "normal", weight: "600", size: "24", color: "#e8eaed" },
    checklist_item: { family: "microsoft-yahei", style: "normal", weight: "400", size: "14", color: "#e8eaed" },
    checklist_item_done: { family: "microsoft-yahei", style: "normal", weight: "400", size: "14", color: "#9aa3ad" },
    comment: { family: "microsoft-yahei", style: "normal", weight: "400", size: "15", color: "#f3f4f6" },
    comment_reply: { family: "microsoft-yahei", style: "normal", weight: "400", size: "14", color: "#e8eaed" },
    description: { family: "microsoft-yahei", style: "normal", weight: "400", size: "15", color: "#1f2328" },
};

const EDITABLE_FONT_SCOPES = [
    {
        id: "board_title",
        label: "看板标题",
        desc: "看板页标题名称（「看板标题：」前缀固定白色，不受此项影响）",
        preview: "个人记录",
        previewWithLabel: true,
    },
    {
        id: "list_title",
        label: "卡片组标题",
        desc: "看板列头列表名称",
        preview: "待办事项",
    },
    {
        id: "card_title_board",
        label: "看板卡片标题",
        desc: "看板上卡片封面标题",
        preview: "完成需求文档",
    },
    {
        id: "card_title_modal",
        label: "卡片弹窗标题",
        desc: "打开卡片后顶部标题输入框",
        preview: "卡片标题",
    },
    {
        id: "checklist_item",
        label: "检查项（未完成）",
        desc: "卡片弹窗内未勾选的检查项",
        preview: "哒哒哒",
    },
    {
        id: "checklist_item_done",
        label: "检查项（已完成）",
        desc: "已勾选、带删除线的检查项",
        preview: "已完成的任务",
    },
    {
        id: "comment",
        label: "评论正文",
        desc: "卡片弹窗顶级评论内容",
        preview: "这是一条评论",
    },
    {
        id: "comment_reply",
        label: "评论回复",
        desc: "评论下方的嵌套回复",
        preview: "回复内容",
    },
    {
        id: "description",
        label: "卡片描述",
        desc: "卡片弹窗描述编辑器正文",
        preview: "描述内容预览",
    },
];

const SETTINGS_TABS = [
    { id: "statuses", label: "看板状态", hash: "#/settings/statuses", icon: "◉" },
    { id: "organizations", label: "所属组织", hash: "#/settings/organizations", icon: "▤" },
    { id: "fonts", label: "字体", hash: "#/settings/fonts", icon: "A" },
    { id: "data-transfer", label: "导入导出", hash: "#/settings/data-transfer", icon: "⇅" },
];

function resolveSettingsTab(hash = location.hash) {
    const normalized = hash.split("?")[0];
    if (normalized.startsWith("#/settings/organizations")) {
        return "organizations";
    }
    if (normalized.startsWith("#/settings/data-transfer")) {
        return "data-transfer";
    }
    if (normalized.startsWith("#/settings/fonts")) {
        return "fonts";
    }
    return "statuses";
}

function resolveEditableFontFamilyStack(familyId) {
    return EDITABLE_FONT_FAMILIES.find((item) => item.id === familyId)?.stack
        || EDITABLE_FONT_FAMILIES[0].stack;
}

function resolveFontFamilyIdFromStack(stack) {
    const normalized = (stack || "").toLowerCase();
    const hit = EDITABLE_FONT_FAMILIES.find((item) => {
        const token = item.stack.split(",")[0].replace(/['"]/g, "").trim().toLowerCase();
        return normalized.includes(token);
    });
    return hit?.id || EDITABLE_FONT_FAMILIES[0].id;
}

function parseFontSizePx(value) {
    const parsed = parseInt(String(value || "").replace("px", ""), 10);
    return Number.isFinite(parsed) ? String(parsed) : "15";
}

function normalizeFontWeight(value) {
    const weight = String(value || "400").trim();
    return weight || "400";
}

function normalizeHexColor(value) {
    const raw = (value || "").trim();
    if (!raw) {
        return "#e8eaed";
    }
    if (raw.startsWith("#")) {
        return raw.length === 7 ? raw.toLowerCase() : raw.slice(0, 7).toLowerCase();
    }
    const match = raw.match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (!match) {
        return "#e8eaed";
    }
    const hex = (part) => Number(part).toString(16).padStart(2, "0");
    return `#${hex(match[1])}${hex(match[2])}${hex(match[3])}`;
}

function readFontProfileFromComputedStyle(scopeId) {
    const prefix = fontScopeCssPrefix(scopeId);
    const styles = getComputedStyle(document.documentElement);
    const fallback = DEFAULT_EDITABLE_FONTS[scopeId];
    return {
        family: resolveFontFamilyIdFromStack(styles.getPropertyValue(`${prefix}-family`).trim()),
        style: styles.getPropertyValue(`${prefix}-style`).trim() || fallback.style,
        weight: normalizeFontWeight(styles.getPropertyValue(`${prefix}-weight`).trim() || fallback.weight),
        size: parseFontSizePx(styles.getPropertyValue(`${prefix}-size`).trim() || `${fallback.size}px`),
        color: normalizeHexColor(styles.getPropertyValue(`${prefix}-color`).trim() || fallback.color),
    };
}

function getEditableFontsSettingsForPanel() {
    const fonts = {};
    for (const scope of EDITABLE_FONT_SCOPES) {
        fonts[scope.id] = readFontProfileFromComputedStyle(scope.id);
    }
    return fonts;
}

function getEditableFontsSettings() {
    const stored = state.settings?.editable_fonts;
    const merged = {};
    for (const scope of EDITABLE_FONT_SCOPES) {
        merged[scope.id] = {
            ...DEFAULT_EDITABLE_FONTS[scope.id],
            ...(stored?.[scope.id] || {}),
        };
    }
    return merged;
}

function fontScopeCssPrefix(scopeId) {
    return `--font-${scopeId.replace(/_/g, "-")}`;
}

function applyFontProfile(scopeId, profile) {
    const prefix = fontScopeCssPrefix(scopeId);
    const root = document.documentElement;
    root.style.setProperty(`${prefix}-family`, resolveEditableFontFamilyStack(profile.family));
    root.style.setProperty(`${prefix}-size`, `${profile.size}px`);
    root.style.setProperty(`${prefix}-style`, profile.style || "normal");
    root.style.setProperty(`${prefix}-weight`, profile.weight || "400");
    root.style.setProperty(`${prefix}-color`, profile.color || DEFAULT_EDITABLE_FONTS[scopeId]?.color);
}

function applyEditableFontSettings() {
    const fonts = getEditableFontsSettings();
    for (const scope of EDITABLE_FONT_SCOPES) {
        applyFontProfile(scope.id, fonts[scope.id]);
    }
}

function buildFontSelectOptions(items, selectedId) {
    return items
        .map((item) => `<option value="${item.id}" ${String(selectedId) === item.id ? "selected" : ""}>${item.label}</option>`)
        .join("");
}

function buildFontSizeOptions(selectedSize) {
    return Array.from({ length: 21 }, (_, index) => index + 12)
        .map((size) => `<option value="${size}" ${String(selectedSize) === String(size) ? "selected" : ""}>${size}px</option>`)
        .join("");
}

function collectFontProfileFromScope(scopeId) {
    const defaults = DEFAULT_EDITABLE_FONTS[scopeId];
    return {
        family: document.getElementById(`font-${scopeId}-family`)?.value || defaults.family,
        style: document.getElementById(`font-${scopeId}-style`)?.value || defaults.style,
        weight: document.getElementById(`font-${scopeId}-weight`)?.value || defaults.weight,
        size: document.getElementById(`font-${scopeId}-size`)?.value || defaults.size,
        color: document.getElementById(`font-${scopeId}-color`)?.value || defaults.color,
    };
}

function collectEditableFontsFromForm() {
    const payload = {};
    for (const scope of EDITABLE_FONT_SCOPES) {
        payload[scope.id] = collectFontProfileFromScope(scope.id);
    }
    return payload;
}

function applyFontStylesToNode(node, font) {
    if (!node) {
        return;
    }
    node.style.fontFamily = resolveEditableFontFamilyStack(font.family);
    node.style.fontSize = `${font.size}px`;
    node.style.fontStyle = font.style;
    node.style.fontWeight = font.weight;
    node.style.color = font.color;
}

function updateFontScopePreview(scopeId) {
    const preview = document.getElementById(`fontPreview-${scopeId}`);
    if (!preview) {
        return;
    }
    const font = collectFontProfileFromScope(scopeId);
    if (scopeId === "board_title") {
        applyFontStylesToNode(preview.querySelector(".board-title-text"), font);
        preview.style.fontFamily = "";
        preview.style.fontSize = "";
        preview.style.fontStyle = "";
        preview.style.fontWeight = "";
        preview.style.color = "";
        preview.style.textDecoration = "";
        return;
    }
    applyFontStylesToNode(preview, font);
    if (scopeId === "checklist_item_done") {
        preview.style.textDecoration = "line-through";
    } else {
        preview.style.textDecoration = "";
    }
}

function updateAllFontScopePreviews() {
    for (const scope of EDITABLE_FONT_SCOPES) {
        updateFontScopePreview(scope.id);
    }
}

function renderFontScopeSection(scope, font) {
    const familyOptions = buildFontSelectOptions(EDITABLE_FONT_FAMILIES, font.family);
    const styleOptions = buildFontSelectOptions(EDITABLE_FONT_STYLES, font.style);
    const weightOptions = buildFontSelectOptions(EDITABLE_FONT_WEIGHTS, font.weight);
    const sizeOptions = buildFontSizeOptions(font.size);
    const previewClass =
        scope.id === "description"
            ? "font-settings-preview font-settings-preview-light"
            : "font-settings-preview";

    const previewContent = scope.previewWithLabel
        ? `<span class="board-title-label">看板标题：</span><span class="board-title-text">${escapeHtml(scope.preview)}</span>`
        : escapeHtml(scope.preview);

    return `
        <section class="font-scope-section" data-font-scope="${scope.id}">
            <div class="font-scope-head">
                <h3 class="font-scope-title">${escapeHtml(scope.label)}</h3>
                <p class="font-scope-desc">${escapeHtml(scope.desc)}</p>
            </div>
            <div class="font-settings-grid">
                <div>
                    <label class="field-label" for="font-${scope.id}-family">字体</label>
                    <select id="font-${scope.id}-family" class="form-select" data-font-field="family">${familyOptions}</select>
                </div>
                <div>
                    <label class="field-label" for="font-${scope.id}-style">字形</label>
                    <select id="font-${scope.id}-style" class="form-select" data-font-field="style">${styleOptions}</select>
                </div>
                <div>
                    <label class="field-label" for="font-${scope.id}-weight">字重</label>
                    <select id="font-${scope.id}-weight" class="form-select" data-font-field="weight">${weightOptions}</select>
                </div>
                <div>
                    <label class="field-label" for="font-${scope.id}-size">字号</label>
                    <select id="font-${scope.id}-size" class="form-select" data-font-field="size">${sizeOptions}</select>
                </div>
                <div>
                    <label class="field-label" for="font-${scope.id}-color">颜色</label>
                    <input id="font-${scope.id}-color" class="form-control form-control-color" type="color" data-font-field="color" value="${escapeHtml(font.color || DEFAULT_EDITABLE_FONTS[scope.id].color)}">
                </div>
            </div>
            <div class="font-settings-preview-wrap">
                <label class="field-label">预览</label>
                <div id="fontPreview-${scope.id}" class="${previewClass}">${previewContent}</div>
            </div>
        </section>
    `;
}

function renderSettingsSidebar(activeTab) {
    return `
        <aside class="settings-sidebar">
            <nav class="settings-nav" aria-label="设置分类">
                ${SETTINGS_TABS.map(
                    (tab) => `
                    <a
                        class="settings-nav-item ${tab.id === activeTab ? "active" : ""}"
                        href="${tab.hash}"
                        aria-current="${tab.id === activeTab ? "page" : "false"}"
                    >
                        <span class="settings-nav-icon" aria-hidden="true">${tab.icon}</span>
                        <span>${tab.label}</span>
                    </a>
                `
                ).join("")}
            </nav>
        </aside>
    `;
}

function renderStatusSettingsPanel(statuses) {
    return `
        <div class="settings-panel">
            <h2>看板状态</h2>
            <p class="panel-desc">配置看板可用的状态枚举。删除已被看板使用的状态时，相关看板会自动迁移到「未设状态」或第一个状态。数据以 Hash 子表保存在 Redis（REDIS_SETTINGS_KEY:board_statuses）。</p>
            <div class="table-responsive">
                <table class="status-settings-table">
                    <thead>
                        <tr>
                            <th>预览</th>
                            <th>名称</th>
                            <th>颜色</th>
                            <th>图标</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="statusSettingsBody">
                        ${statuses.map((item) => renderStatusSettingsRow(item)).join("")}
                    </tbody>
                </table>
            </div>
            <div class="settings-toolbar">
                <button class="btn btn-outline-primary" id="addStatusRowBtn" type="button">+ 添加状态</button>
                <button class="btn btn-primary" id="saveStatusSettingsBtn" type="button">保存状态设置</button>
            </div>
        </div>
    `;
}

function renderFontSettingsPanel(fonts = getEditableFontsSettingsForPanel()) {
    return `
        <div class="settings-panel">
            <h2>字体</h2>
            <p class="panel-desc">
                按界面区域分别配置字体。表单初始值读取当前页面<strong>正在生效</strong>的样式，与各区域实际显示一致；修改后点保存才会写入 Redis。
            </p>
            <div class="font-scope-list">
                ${EDITABLE_FONT_SCOPES.map((scope) => renderFontScopeSection(scope, fonts[scope.id])).join("")}
            </div>
            <div class="settings-toolbar">
                <button class="btn btn-outline-secondary" id="resetEditableFontBtn" type="button">全部恢复默认</button>
                <button class="btn btn-primary" id="saveEditableFontBtn" type="button">保存字体设置</button>
            </div>
        </div>
    `;
}

function renderDataTransferPanel() {
    const organizations = getOrganizations();
    const boards = state.boards || [];
    const orgOptions = [
        `<option value="org_0">${escapeHtml(PERSONAL_BOARD_ORGANIZATION)}</option>`,
        ...organizations.map(
            (org) => `<option value="${escapeHtml(org.id)}">${escapeHtml(org.name)}</option>`
        ),
    ].join("");
    const boardOptions = boards.length
        ? boards.map((board) => `<option value="${escapeHtml(board.id)}">${escapeHtml(board.title)}</option>`).join("")
        : `<option value="">暂无看板</option>`;

    return `
        <div class="settings-panel">
            <h2>数据导入导出</h2>
            <p class="panel-desc">
                支持三种 .dat 数据包：<strong>系统全量</strong>、<strong>组织</strong>、<strong>单看板</strong>。
                文件为 UTF-8 JSON，首行魔数 <code>BFLOW1</code>，含 SHA256 校验和。导入前会先执行完整性检查。
            </p>

            <div class="transfer-section">
                <h3>系统全量</h3>
                <p class="transfer-desc">
                    导出全部看板、列表、卡片，以及<strong>系统设置</strong>（看板状态、卡片类型、组织列表、字体设置）和 ID 计数器。
                    导入将<strong>完全覆盖</strong>当前系统数据（含上述设置）。
                </p>
                <div class="transfer-actions">
                    <button class="btn btn-outline-primary" id="exportSystemBtn" type="button">导出系统 .dat</button>
                    <label class="btn btn-outline-secondary transfer-file-btn">
                        选择系统包…
                        <input id="importSystemFile" type="file" accept=".dat,application/json,text/plain" hidden>
                    </label>
                    <button class="btn btn-danger" id="importSystemBtn" type="button" disabled>校验通过后覆盖导入</button>
                </div>
                <div class="transfer-report" id="importSystemReport"></div>
            </div>

            <div class="transfer-section">
                <h3>组织</h3>
                <p class="transfer-desc">仅导出/导入选定组织下的看板数据。导入默认合并；可选覆盖该组织下已有看板。</p>
                <div class="transfer-field-row">
                    <label class="field-label" for="exportOrgSelect">选择组织</label>
                    <select id="exportOrgSelect" class="form-select">${orgOptions}</select>
                </div>
                <div class="transfer-actions">
                    <button class="btn btn-outline-primary" id="exportOrgBtn" type="button">导出组织 .dat</button>
                    <label class="btn btn-outline-secondary transfer-file-btn">
                        选择组织包…
                        <input id="importOrgFile" type="file" accept=".dat,application/json,text/plain" hidden>
                    </label>
                    <select id="importOrgMode" class="form-select form-select-sm transfer-mode-select">
                        <option value="merge">合并导入</option>
                        <option value="replace">覆盖该组织看板</option>
                    </select>
                    <button class="btn btn-primary" id="importOrgBtn" type="button" disabled>校验通过后导入</button>
                </div>
                <div class="transfer-report" id="importOrgReport"></div>
            </div>

            <div class="transfer-section">
                <h3>单看板</h3>
                <p class="transfer-desc">导出单个看板及其列表、卡片（含画布/脑图/表格/描述表格数据）。</p>
                <div class="transfer-field-row">
                    <label class="field-label" for="exportBoardSelect">选择看板</label>
                    <select id="exportBoardSelect" class="form-select">${boardOptions}</select>
                </div>
                <div class="transfer-actions">
                    <button class="btn btn-outline-primary" id="exportBoardBtn" type="button" ${boards.length ? "" : "disabled"}>导出看板 .dat</button>
                    <label class="btn btn-outline-secondary transfer-file-btn">
                        选择看板包…
                        <input id="importBoardFile" type="file" accept=".dat,application/json,text/plain" hidden>
                    </label>
                    <select id="importBoardMode" class="form-select form-select-sm transfer-mode-select">
                        <option value="merge">合并导入（自动分配新 ID）</option>
                        <option value="replace">同 ID 覆盖</option>
                    </select>
                    <button class="btn btn-primary" id="importBoardBtn" type="button" disabled>校验通过后导入</button>
                </div>
                <div class="transfer-report" id="importBoardReport"></div>
            </div>
        </div>
    `;
}

function renderTransferReport(container, validation) {
    if (!container) {
        return;
    }
    if (!validation) {
        container.innerHTML = "";
        container.className = "transfer-report";
        return;
    }

    const summaryLabels = {
        boards: "看板",
        lists: "列表",
        cards: "卡片",
        organizations: "组织",
        card_types: "卡片类型",
        board_statuses: "看板状态",
        board_title: "看板标题",
        organization: "组织名称",
    };

    const statusClass = validation.valid ? "is-valid" : "is-invalid";
    const summary = validation.summary || {};
    const summaryItems = Object.entries(summary)
        .filter(([key]) => !["label", "exported_at"].includes(key))
        .map(([key, value]) => {
            const label = summaryLabels[key] || key;
            return `<li><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong></li>`;
        })
        .join("");

    container.className = `transfer-report ${statusClass}`;
    container.innerHTML = `
        <div class="transfer-report-head">
            <strong>${validation.valid ? "校验通过" : "校验失败"}</strong>
            <span>${escapeHtml(validation.kind || "")} 包</span>
        </div>
        ${summaryItems ? `<ul class="transfer-report-summary">${summaryItems}</ul>` : ""}
        ${
            validation.errors?.length
                ? `<ul class="transfer-report-errors">${validation.errors.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : ""
        }
        ${
            validation.warnings?.length
                ? `<ul class="transfer-report-warnings">${validation.warnings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
                : ""
        }
    `;
}

function downloadDat(url, fallbackName) {
    return fetch(url)
        .then(async (response) => {
            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                throw new Error(payload.message || "导出失败");
            }
            const blob = await response.blob();
            const filename =
                response.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/)?.[1] || fallbackName;
            const link = document.createElement("a");
            link.href = URL.createObjectURL(blob);
            link.download = filename;
            document.body.appendChild(link);
            link.click();
            link.remove();
            URL.revokeObjectURL(link.href);
        });
}

async function validateTransferFile(file, expectedKind) {
    const formData = new FormData();
    formData.append("file", file);
    if (expectedKind) {
        formData.append("expected_kind", expectedKind);
    }
    const response = await fetch("/api/data-transfer/validate", {
        method: "POST",
        body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || "校验请求失败");
    }
    return payload;
}

async function importTransferFile(file, { expectedKind, mode }) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("mode", mode);
    if (expectedKind) {
        formData.append("expected_kind", expectedKind);
    }
    const response = await fetch("/api/data-transfer/import", {
        method: "POST",
        body: formData,
    });
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || "导入失败");
    }
    return payload;
}

function bindDataTransferPanel() {
    const transferState = {
        system: { file: null, validation: null },
        organization: { file: null, validation: null },
        board: { file: null, validation: null },
    };

    const exportSystemBtn = document.getElementById("exportSystemBtn");
    const exportOrgBtn = document.getElementById("exportOrgBtn");
    const exportBoardBtn = document.getElementById("exportBoardBtn");
    const exportOrgSelect = document.getElementById("exportOrgSelect");
    const exportBoardSelect = document.getElementById("exportBoardSelect");

    exportSystemBtn?.addEventListener("click", () => {
        downloadDat("/api/data-transfer/export/system", "boardflow-system.dat")
            .then(() => showSuccess("系统数据包已开始下载"))
            .catch((error) => showError(error.message || "导出失败"));
    });

    exportOrgBtn?.addEventListener("click", () => {
        const orgId = exportOrgSelect?.value;
        if (!orgId) {
            showError("请选择组织");
            return;
        }
        downloadDat(`/api/data-transfer/export/organization/${encodeURIComponent(orgId)}`, "boardflow-org.dat")
            .then(() => showSuccess("组织数据包已开始下载"))
            .catch((error) => showError(error.message || "导出失败"));
    });

    exportBoardBtn?.addEventListener("click", () => {
        const boardId = exportBoardSelect?.value;
        if (!boardId) {
            showError("请选择看板");
            return;
        }
        downloadDat(`/api/data-transfer/export/board/${encodeURIComponent(boardId)}`, "boardflow-board.dat")
            .then(() => showSuccess("看板数据包已开始下载"))
            .catch((error) => showError(error.message || "导出失败"));
    });

    function wireImport(kind, fileInputId, reportId, importBtnId, modeSelectId) {
        const fileInput = document.getElementById(fileInputId);
        const reportEl = document.getElementById(reportId);
        const importBtn = document.getElementById(importBtnId);
        const modeSelect = document.getElementById(modeSelectId);

        fileInput?.addEventListener("change", async () => {
            const file = fileInput.files?.[0];
            transferState[kind].file = file || null;
            transferState[kind].validation = null;
            if (importBtn) {
                importBtn.disabled = true;
            }
            renderTransferReport(reportEl, null);
            if (!file) {
                return;
            }
            try {
                const validation = await validateTransferFile(file, kind === "system" ? "system" : kind);
                transferState[kind].validation = validation;
                renderTransferReport(reportEl, validation);
                if (importBtn) {
                    importBtn.disabled = !validation.valid;
                }
            } catch (error) {
                renderTransferReport(reportEl, {
                    valid: false,
                    kind,
                    errors: [error.message || "校验失败"],
                    warnings: [],
                    summary: {},
                });
            }
        });

        importBtn?.addEventListener("click", async () => {
            const file = transferState[kind].file;
            const validation = transferState[kind].validation;
            if (!file || !validation?.valid) {
                showError("请先选择并通过校验的数据包");
                return;
            }
            const mode =
                kind === "system" ? "replace" : modeSelect?.value || (kind === "organization" ? "merge" : "merge");
            const confirmText =
                kind === "system"
                    ? "确定用该系统包完全覆盖当前所有数据吗？此操作不可撤销。"
                    : kind === "organization"
                      ? mode === "replace"
                          ? "确定覆盖该组织下已有看板并导入新数据吗？"
                          : "确定合并导入该组织数据包吗？"
                      : mode === "replace"
                        ? "确定覆盖同 ID 看板并导入吗？"
                        : "确定合并导入该看板数据包吗？";

            if (!window.confirm(confirmText)) {
                return;
            }

            importBtn.disabled = true;
            try {
                await importTransferFile(file, {
                    expectedKind: kind === "system" ? "system" : kind,
                    mode,
                });
                await loadSettings();
                await loadBoards();
                showSuccess("数据导入成功");
                if (kind === "system") {
                    renderRoute();
                    return;
                }
                renderSettingsPage("data-transfer");
            } catch (error) {
                showError(error.message || "导入失败");
                importBtn.disabled = false;
            }
        });
    }

    wireImport("system", "importSystemFile", "importSystemReport", "importSystemBtn");
    wireImport("organization", "importOrgFile", "importOrgReport", "importOrgBtn", "importOrgMode");
    wireImport("board", "importBoardFile", "importBoardReport", "importBoardBtn", "importBoardMode");
}

function renderOrganizationSettingsPanel(organizations) {
    return `
        <div class="settings-panel">
            <h2>所属组织</h2>
            <p class="panel-desc">「个人看板」为内置默认选项。此处维护公司/团队组织，保存后可在新建或编辑看板时选择（REDIS_SETTINGS_KEY:organizations）。</p>
            <div class="table-responsive">
                <table class="organization-settings-table">
                    <thead>
                        <tr>
                            <th>组织名称</th>
                            <th>备注</th>
                            <th>操作</th>
                        </tr>
                    </thead>
                    <tbody id="organizationSettingsBody">
                        ${
                            organizations.length
                                ? organizations.map((item) => renderOrganizationSettingsRow(item)).join("")
                                : renderOrganizationSettingsRow()
                        }
                    </tbody>
                </table>
            </div>
            <div class="settings-toolbar">
                <button class="btn btn-outline-primary" id="addOrganizationRowBtn" type="button">+ 添加组织</button>
                <button class="btn btn-primary" id="saveOrganizationSettingsBtn" type="button">保存组织设置</button>
            </div>
        </div>
    `;
}

async function saveEditableFontSettings() {
    const payload = collectEditableFontsFromForm();
    try {
        const result = await api("/api/settings/editable-fonts", {
            method: "PUT",
            body: JSON.stringify({ editable_fonts: payload }),
        });
        state.settings = result.settings || state.settings;
        applyEditableFontSettings();
        showSuccess(result.message || "字体设置已保存");
    } catch (error) {
        showError(error.message || "保存字体设置失败");
    }
}

function bindFontSettingsPanel() {
    document.querySelectorAll("[data-font-scope] [data-font-field]").forEach((node) => {
        const section = node.closest("[data-font-scope]");
        const scopeId = section?.dataset.fontScope;
        if (!scopeId) {
            return;
        }
        node.addEventListener("input", () => updateFontScopePreview(scopeId));
        node.addEventListener("change", () => updateFontScopePreview(scopeId));
    });
    document.getElementById("saveEditableFontBtn")?.addEventListener("click", () => {
        saveEditableFontSettings().catch((error) => showError(error.message || "保存字体设置失败"));
    });
    document.getElementById("resetEditableFontBtn")?.addEventListener("click", () => {
        for (const scope of EDITABLE_FONT_SCOPES) {
            const defaults = DEFAULT_EDITABLE_FONTS[scope.id];
            const family = document.getElementById(`font-${scope.id}-family`);
            const style = document.getElementById(`font-${scope.id}-style`);
            const weight = document.getElementById(`font-${scope.id}-weight`);
            const size = document.getElementById(`font-${scope.id}-size`);
            const color = document.getElementById(`font-${scope.id}-color`);
            if (family) family.value = defaults.family;
            if (style) style.value = defaults.style;
            if (weight) weight.value = defaults.weight;
            if (size) size.value = defaults.size;
            if (color) color.value = defaults.color;
        }
        updateAllFontScopePreviews();
    });
    updateAllFontScopePreviews();
}

function renderSettingsPage(activeTab = resolveSettingsTab()) {
    state.currentBoardId = null;
    state.currentBoard = null;
    clearError();
    const statuses = getBoardStatuses();
    const organizations = getOrganizations();
    const panelHtml =
        activeTab === "data-transfer"
            ? renderDataTransferPanel()
            : activeTab === "organizations"
              ? renderOrganizationSettingsPanel(organizations)
              : activeTab === "fonts"
                ? renderFontSettingsPanel()
                : renderStatusSettingsPanel(statuses);

    appView.innerHTML = `
        <section class="settings-page">
            <div class="page-head">
                <div>
                    <a class="back-link d-inline-block mb-2" href="${getBoardHubBackHref()}">← 返回看板列表</a>
                    <h1>设置</h1>
                </div>
            </div>
            <div class="settings-layout">
                ${renderSettingsSidebar(activeTab)}
                <div class="settings-main">
                    ${panelHtml}
                </div>
            </div>
        </section>
    `;

    if (activeTab === "data-transfer") {
        bindDataTransferPanel();
        return;
    }

    if (activeTab === "fonts") {
        bindFontSettingsPanel();
        return;
    }

    if (activeTab === "organizations") {
        document.getElementById("addOrganizationRowBtn").addEventListener("click", addOrganizationSettingsRow);
        document.getElementById("saveOrganizationSettingsBtn").addEventListener("click", saveOrganizationSettings);
        bindOrganizationSettingsRows();
        return;
    }

    document.getElementById("addStatusRowBtn").addEventListener("click", addStatusSettingsRow);
    document.getElementById("saveStatusSettingsBtn").addEventListener("click", saveStatusSettings);
    bindStatusSettingsRows();
}

function bindStatusSettingsRow(row) {
    if (row.dataset.bound === "1") {
        return;
    }
    row.dataset.bound = "1";

    const updatePreview = () => {
        const label = row.querySelector(".status-label-input")?.value.trim() || "新状态";
        const color = row.querySelector(".status-color-input")?.value || "#9ca3af";
        const icon = row.querySelector(".status-icon-input")?.value || "circle";
        const preview = row.querySelector(".status-preview");
        if (preview) {
            preview.innerHTML = `${renderStatusIcon({ color, icon })}${escapeHtml(label)}`;
        }
    };

    row.querySelectorAll(".status-label-input, .status-color-input, .status-icon-input").forEach((input) => {
        input.addEventListener("input", updatePreview);
        input.addEventListener("change", updatePreview);
    });

    row.querySelector(".status-delete-btn")?.addEventListener("click", () => {
        const body = document.getElementById("statusSettingsBody");
        if (!body || body.querySelectorAll("tr").length <= 1) {
            showError("至少保留一个看板状态");
            return;
        }
        row.remove();
    });
}

function bindStatusSettingsRows() {
    document.querySelectorAll("#statusSettingsBody tr").forEach(bindStatusSettingsRow);
}

function renderStatusSettingsRow(item) {
    const status = item || { id: "", label: "", color: "#9ca3af", icon: "circle" };
    return `
        <tr data-status-id="${escapeHtml(status.id)}">
            <td class="status-preview-cell">
                <span class="board-status-pill status-preview">${renderStatusIcon(status)}${escapeHtml(status.label || "新状态")}</span>
            </td>
            <td>
                <input class="form-control status-label-input" value="${escapeHtml(status.label)}" placeholder="状态名称">
            </td>
            <td>
                <input class="form-control form-control-color status-color-input" type="color" value="${escapeHtml(status.color || "#9ca3af")}">
            </td>
            <td>
                <select class="form-select status-icon-input">
                    ${STATUS_ICON_OPTIONS.map(
                        (option) => `
                        <option value="${option.id}" ${option.id === status.icon ? "selected" : ""}>${option.label}</option>
                    `
                    ).join("")}
                </select>
            </td>
            <td>
                <button class="btn btn-sm btn-outline-danger status-delete-btn" type="button">删除</button>
            </td>
        </tr>
    `;
}

function addStatusSettingsRow() {
    const body = document.getElementById("statusSettingsBody");
    if (!body) {
        return;
    }
    body.insertAdjacentHTML("beforeend", renderStatusSettingsRow({ id: "", label: "", color: "#58a6ff", icon: "circle" }));
    const rows = body.querySelectorAll("tr");
    bindStatusSettingsRow(rows[rows.length - 1]);
}

function collectStatusSettingsRows() {
    return [...document.querySelectorAll("#statusSettingsBody tr")].map((row) => ({
        id: row.dataset.statusId || "",
        label: row.querySelector(".status-label-input")?.value.trim() || "",
        color: row.querySelector(".status-color-input")?.value || "#9ca3af",
        icon: row.querySelector(".status-icon-input")?.value || "circle",
    }));
}

async function saveStatusSettings() {
    const board_statuses = collectStatusSettingsRows();
    if (!board_statuses.length) {
        showError("至少保留一个看板状态");
        return;
    }
    if (board_statuses.some((item) => !item.label)) {
        showError("请填写所有状态名称");
        return;
    }

    try {
        const result = await api("/api/settings/board-statuses", {
            method: "PUT",
            body: JSON.stringify({ board_statuses }),
        });
        state.settings = { ...state.settings, ...result.settings };
        await loadBoards();
        renderSettingsPage("statuses");
        showSuccess("看板状态已保存");
    } catch (error) {
        showError(error.message || "保存设置失败");
    }
}

function renderOrganizationSettingsRow(item) {
    const organization = item || { id: "", name: "", note: "" };
    return `
        <tr data-organization-id="${escapeHtml(organization.id)}">
            <td>
                <input class="form-control organization-name-input" value="${escapeHtml(organization.name)}" placeholder="例如：壮游科技">
            </td>
            <td>
                <input class="form-control organization-note-input" value="${escapeHtml(organization.note || "")}" placeholder="可选备注">
            </td>
            <td>
                <button class="btn btn-sm btn-outline-danger organization-delete-btn" type="button">删除</button>
            </td>
        </tr>
    `;
}

function bindOrganizationSettingsRow(row) {
    if (row.dataset.bound === "1") {
        return;
    }
    row.dataset.bound = "1";

    row.querySelector(".organization-delete-btn")?.addEventListener("click", () => {
        row.remove();
    });
}

function bindOrganizationSettingsRows() {
    document.querySelectorAll("#organizationSettingsBody tr").forEach(bindOrganizationSettingsRow);
}

function addOrganizationSettingsRow() {
    const body = document.getElementById("organizationSettingsBody");
    if (!body) {
        return;
    }
    body.insertAdjacentHTML("beforeend", renderOrganizationSettingsRow());
    const rows = body.querySelectorAll("tr");
    bindOrganizationSettingsRow(rows[rows.length - 1]);
}

function collectOrganizationSettingsRows() {
    return [...document.querySelectorAll("#organizationSettingsBody tr")]
        .map((row) => ({
            id: row.dataset.organizationId || "",
            name: row.querySelector(".organization-name-input")?.value.trim() || "",
            note: row.querySelector(".organization-note-input")?.value.trim() || "",
        }))
        .filter((item) => item.name);
}

async function saveOrganizationSettings() {
    const organizations = collectOrganizationSettingsRows();
    if (organizations.some((item) => !item.name)) {
        showError("请填写所有组织名称");
        return;
    }

    try {
        const result = await api("/api/settings/organizations", {
            method: "PUT",
            body: JSON.stringify({ organizations }),
        });
        state.settings = { ...state.settings, ...result.settings };
        await loadBoards();
        renderSettingsPage("organizations");
        showSuccess("组织列表已保存");
    } catch (error) {
        showError(error.message || "保存组织失败");
    }
}

async function loadBoards() {
    const data = await api("/api/boards");
    state.boards = data.items || [];
}

function renderBoardList() {
    clearError();
    renderBoardListContent();
}

function renderBoardHubSidebar(hub = state.boardHub) {
    const organizations = getOrganizations();
    const mineExpanded = state.boardHubGroups.mine;
    const projectsExpanded = state.boardHubGroups.projects;

    return `
        <aside class="board-hub-sidebar">
            <div class="board-hub-sidebar-head">
                <button class="board-hub-menu-btn" type="button" aria-label="菜单">☰</button>
            </div>
            <nav class="board-hub-nav">
                <a
                    class="board-hub-nav-item ${hub.scope === "workbench" ? "active" : ""}"
                    href="${buildBoardHubHref("workbench")}"
                >
                    <span class="board-hub-nav-icon" aria-hidden="true">▦</span>
                    <span>工作台</span>
                </a>

                <div class="board-hub-nav-group ${mineExpanded ? "expanded" : ""}">
                    <button class="board-hub-nav-group-head" data-toggle-hub-group="mine" type="button">
                        <span class="board-hub-nav-group-label">
                            <span class="board-hub-nav-icon" aria-hidden="true">◉</span>
                            <span>我的</span>
                        </span>
                        <span class="board-hub-nav-caret" aria-hidden="true">▾</span>
                    </button>
                    <div class="board-hub-nav-group-body">
                        <a
                            class="board-hub-nav-subitem ${hub.scope === "personal" ? "active" : ""}"
                            href="${buildBoardHubHref("personal")}"
                        >个人看板</a>
                        <a
                            class="board-hub-nav-subitem ${hub.scope === "starred" ? "active" : ""}"
                            href="${buildBoardHubHref("starred")}"
                        >星标看板</a>
                    </div>
                </div>

                <div class="board-hub-nav-group ${projectsExpanded ? "expanded" : ""}">
                    <button class="board-hub-nav-group-head" data-toggle-hub-group="projects" type="button">
                        <span class="board-hub-nav-group-label">
                            <span class="board-hub-nav-icon" aria-hidden="true">▤</span>
                            <span>项目</span>
                        </span>
                        <span class="board-hub-nav-caret" aria-hidden="true">▾</span>
                    </button>
                    <div class="board-hub-nav-group-body">
                        ${
                            organizations.length
                                ? organizations
                                      .map(
                                          (item) => `
                            <a
                                class="board-hub-nav-subitem ${
                                    hub.scope === "org" && hub.orgName === item.name ? "active" : ""
                                }"
                                href="${buildBoardHubHref("org", item.name)}"
                                title="${escapeHtml(item.note || item.name)}"
                            >${escapeHtml(item.name)}</a>
                        `
                                      )
                                      .join("")
                                : `<span class="board-hub-nav-empty">暂无组织，请先在设置中添加</span>`
                        }
                    </div>
                </div>
            </nav>
        </aside>
    `;
}

function renderBoardHubHeader(hub = state.boardHub) {
    const title = getBoardHubTitle(hub);
    const icon =
        hub.scope === "starred"
            ? "★"
            : hub.scope === "personal"
              ? "◉"
              : hub.scope === "workbench"
                ? "▦"
                : "▤";
    const sortBy = hub.sortBy;

    return `
        <header class="board-hub-header">
            <div class="board-hub-header-title">
                <span class="board-hub-header-icon" aria-hidden="true">${icon}</span>
                <h1>${escapeHtml(title)}</h1>
            </div>
            <div class="board-hub-toolbar">
                <button class="board-hub-tool-btn" id="boardHubFilterBtn" type="button" title="筛选">
                    <span aria-hidden="true">⛃</span>
                    <span>筛选</span>
                </button>
                <button
                    class="board-hub-tool-btn ${sortBy === "time" ? "active" : ""}"
                    data-hub-sort="time"
                    type="button"
                >时间</button>
                <button
                    class="board-hub-tool-btn ${sortBy === "name" ? "active" : ""}"
                    data-hub-sort="name"
                    type="button"
                >名称</button>
                <button
                    class="board-hub-tool-btn ${sortBy === "custom" ? "active" : ""}"
                    data-hub-sort="custom"
                    type="button"
                >自定义</button>
                <button class="board-hub-tool-btn board-hub-tool-icon" id="createBoardHubBtn" type="button" title="新建看板">+</button>
                <button class="board-hub-tool-btn board-hub-tool-icon" type="button" title="更多">⋯</button>
            </div>
        </header>
    `;
}

function renderBoardStarButton(boardId, { className = "board-hub-star" } = {}) {
    const starred = isBoardStarred(boardId);
    return `
        <button
            class="${className} ${starred ? "starred" : ""}"
            data-action="toggle-star"
            data-board-id="${boardId}"
            type="button"
            title="${starred ? "取消星标" : "加入星标看板"}"
            aria-label="${starred ? "取消星标" : "加入星标看板"}"
        >${starred ? "★" : "☆"}</button>
    `;
}

function renderBoardHubCard(board) {
    return `
        <article class="board-hub-card" data-board-id="${board.id}">
            <h3 class="board-hub-card-title">${escapeHtml(board.title)}</h3>
            <div class="board-hub-card-footer">
                <div class="board-hub-card-hover-actions">
                    <button class="btn btn-sm btn-light" data-action="edit-board" data-board-id="${board.id}" type="button">编辑</button>
                    <button class="btn btn-sm btn-outline-light" data-action="delete-board" data-board-id="${board.id}" type="button">删除</button>
                </div>
                <div class="board-hub-card-actions">
                    ${renderBoardStarButton(board.id)}
                </div>
            </div>
        </article>
    `;
}

function renderBoardHubEmpty(hub = state.boardHub) {
    if (hub.scope === "starred") {
        return `
            <div class="board-hub-empty">
                <h3>暂无星标看板</h3>
                <p>在看板卡片右下角点击 ☆，或将看板页右上角的星标点亮，即可加入星标看板。</p>
            </div>
        `;
    }
    return `
        <div class="board-hub-empty">
            <h3>还没有看板</h3>
            <p>点击右上角「+」为「${escapeHtml(getBoardHubTitle(hub))}」创建第一个看板</p>
        </div>
    `;
}

function bindBoardHubEvents() {
    document.querySelectorAll("[data-toggle-hub-group]").forEach((node) => {
        node.addEventListener("click", () => {
            const key = node.dataset.toggleHubGroup;
            if (!key || !(key in state.boardHubGroups)) {
                return;
            }
            state.boardHubGroups[key] = !state.boardHubGroups[key];
            renderBoardListContent();
        });
    });

    document.querySelectorAll("[data-hub-sort]").forEach((node) => {
        node.addEventListener("click", () => {
            state.boardHub.sortBy = node.dataset.hubSort || "custom";
            renderBoardListContent();
        });
    });

    document.getElementById("createBoardHubBtn")?.addEventListener("click", () => {
        openBoardForm().catch((error) => showError(error.message || "打开看板表单失败"));
    });
    document.getElementById("boardHubFilterBtn")?.addEventListener("click", () => {
        showSuccess("筛选功能即将支持");
    });
}

function renderBoardListContent() {
    state.currentBoardId = null;
    state.currentBoard = null;
    const hub = state.boardHub;
    const visibleBoards = sortBoardsForHub(filterBoardsForHub(state.boards, hub), hub.sortBy);

    appView.innerHTML = `
        <section class="board-hub-page">
            ${renderBoardHubSidebar(hub)}
            <div class="board-hub-main">
                ${renderBoardHubHeader(hub)}
                <div class="board-hub-grid" id="boardGrid">
                    ${
                        visibleBoards.length
                            ? visibleBoards.map(renderBoardHubCard).join("")
                            : renderBoardHubEmpty(hub)
                    }
                </div>
            </div>
        </section>
    `;

    bindBoardHubEvents();

    document.querySelectorAll("[data-board-id]").forEach((node) => {
        node.addEventListener("click", (event) => {
            if (event.target.closest("[data-action]")) {
                return;
            }
            location.hash = `#/board/${node.dataset.boardId}`;
        });
    });
    document.querySelectorAll("[data-action='toggle-star']").forEach((node) => {
        node.addEventListener("click", (event) => {
            event.stopPropagation();
            toggleBoardStar(node.dataset.boardId);
            if (state.currentBoardId && String(state.currentBoardId) === String(node.dataset.boardId)) {
                renderBoardPage();
                return;
            }
            renderBoardListContent();
            showSuccess(isBoardStarred(node.dataset.boardId) ? "已加入星标看板" : "已取消星标");
        });
    });
    document.querySelectorAll("[data-action='edit-board']").forEach((node) => {
        node.addEventListener("click", (event) => {
            event.stopPropagation();
            openBoardForm(node.dataset.boardId).catch((error) =>
                showError(error.message || "打开看板表单失败")
            );
        });
    });
    document.querySelectorAll("[data-action='delete-board']").forEach((node) => {
        node.addEventListener("click", async (event) => {
            event.stopPropagation();
            if (!confirm("确定删除该看板吗？")) {
                return;
            }
            await api(`/api/boards/${node.dataset.boardId}`, { method: "DELETE" });
            showSuccess("看板已删除");
            await loadBoards();
            renderBoardListContent();
        });
    });
}

function renderBoardViewTabs(activeView = "kanban") {
    const tabs = [
        { id: "kanban", label: "看板", enabled: true },
        { id: "canvas", label: "画布", enabled: true },
        { id: "timeline", label: "时间线", enabled: false },
        { id: "table", label: "表格", enabled: true },
        { id: "mindmap", label: "思维导图", enabled: true },
        { id: "stats", label: "统计", enabled: false },
    ];

    return `
        <div class="view-tabs" role="tablist" aria-label="看板视图">
            ${tabs
                .map(
                    (tab) => `
                <button
                    class="view-tab ${tab.id === activeView ? "active" : ""}"
                    type="button"
                    data-view-tab="${tab.id}"
                    ${tab.enabled ? "" : 'disabled title="即将支持"'}
                >${tab.label}</button>
            `
                )
                .join("")}
        </div>
    `;
}

function saveBoardViewPreference(boardId, view) {
    if (!boardId || !view) {
        return;
    }
    sessionStorage.setItem(`boardflow-view-${boardId}`, view);
}

function loadBoardViewPreference(boardId) {
    return sessionStorage.getItem(`boardflow-view-${boardId}`) || "kanban";
}

function bindBoardViewTabs() {
    document.querySelectorAll("[data-view-tab]").forEach((button) => {
        button.addEventListener("click", () => {
            if (button.disabled) {
                return;
            }
            state.currentBoardView = button.dataset.viewTab;
            saveBoardViewPreference(state.currentBoardId, state.currentBoardView);
            renderBoardPage();
        });
    });
}

async function openBoard(boardId, cardId = null) {
    try {
        const data = await api(`/api/boards/${boardId}`);
        state.currentBoardId = boardId;
        state.currentBoard = data;
        state.currentBoardView = loadBoardViewPreference(boardId);
        clearError();
        renderBoardPage();
        if (cardId) {
            const card = findCard(cardId);
            if (card) {
                openCardForBoardView(cardId);
            }
        }
    } catch (error) {
        showError(error.message || "加载看板失败");
        state.currentBoardId = null;
        state.currentBoard = null;
        destroySortables();
        renderBoardListContent();
        if (location.hash !== getBoardHubBackHref()) {
            history.replaceState(null, "", getBoardHubBackHref());
        }
    }
}

function renderBoardPage() {
    const { board, lists, settings } = state.currentBoard;
    state.settings = { ...state.settings, ...settings };
    const dateRange = formatDateRange(board.start_date, board.end_date);
    const activeView = state.currentBoardView || "kanban";
    const isEditorView = isEditorBoardView(activeView);

    appView.innerHTML = `
        <section class="board-page">
            <div class="board-toolbar">
                <div class="board-toolbar-nav">
                    <a class="back-link" href="${getBoardHubBackHref()}">← 返回看板列表</a>
                    <div class="toolbar-actions">
                        ${renderBoardStarButton(board.id, { className: "board-toolbar-star" })}
                        <button class="btn btn-sm btn-light" id="editCurrentBoardBtn" type="button">编辑看板</button>
                    </div>
                </div>
                <div class="board-title-block">
                    <div class="board-title-row">
                        <div class="board-title-heading">
                            <h2>
                                <span class="board-title-label">看板标题：</span><span class="board-title-text">${escapeHtml(board.title)}</span>
                            </h2>
                            <div class="board-title-meta">${renderBoardTitleMeta(board)}</div>
                        </div>
                        ${renderBoardViewTabs(activeView)}
                    </div>
                    ${dateRange ? `<p class="board-subtitle">项目周期：${dateRange}</p>` : ""}
                </div>
            </div>
            <div class="kanban-scroll">
                <div class="kanban-board ${activeView === "canvas" ? "canvas-mode" : ""} ${activeView === "mindmap" ? "mindmap-mode" : ""} ${activeView === "table" ? "table-mode" : ""}" id="kanbanBoard">
                    ${lists.map((list) => renderKanbanList(list, settings, { viewMode: activeView })).join("")}
                    <div class="add-list-column">
                        <button class="add-list-btn" data-action="add-list" id="addListBtn" type="button">+ 添加列表</button>
                    </div>
                </div>
            </div>
        </section>
    `;

    document.getElementById("editCurrentBoardBtn").addEventListener("click", () => {
        openBoardForm(board.id).catch((error) => showError(error.message || "打开看板表单失败"));
    });
    bindBoardStatusDropdown();
    bindBoardOrgDropdown();
    bindBoardViewTabs();
    if (!isEditorView) {
        initSortables();
    }
}

function renderKanbanList(list, settings, { viewMode = "kanban" } = {}) {
    return `
        <section class="kanban-list" data-list-id="${list.id}">
            <div class="list-header">
                <div>
                    <h3>${escapeHtml(list.title)}<span class="list-count">${list.cards.length}</span></h3>
                </div>
                <div class="list-menu-dropdown">
                    <button class="list-menu-btn" data-action="toggle-list-menu" data-list-id="${list.id}" type="button" title="列表菜单">☰</button>
                    <div class="list-menu-panel" data-list-menu="${list.id}">
                        <button class="list-menu-option" data-action="rename-list" data-list-id="${list.id}" type="button">重命名</button>
                        <button class="list-menu-option list-menu-option-danger" data-action="delete-list" data-list-id="${list.id}" type="button">删除列表</button>
                    </div>
                </div>
            </div>
            <div class="list-cards" data-list-id="${list.id}">
                ${list.cards.map((card) => renderKanbanCard(card, settings, { viewMode })).join("")}
            </div>
            <div class="list-footer">
                <button class="add-card-btn" data-action="add-card" data-list-id="${list.id}" type="button">+ 添加卡片</button>
            </div>
        </section>
    `;
}

function renderKanbanCard(card, settings, { viewMode = "kanban" } = {}) {
    const type = (settings.card_types || []).find((item) => item.id === card.type) || { label: card.type, color: "#16a34a" };
    const viewActions = renderCardViewActions(card, viewMode);
    const cardClasses = [
        viewMode === "canvas" ? "kanban-card-canvas" : "",
        viewMode === "mindmap" ? "kanban-card-mindmap" : "",
        viewMode === "table" ? "kanban-card-table" : "",
        viewActions ? "has-view-actions" : "",
    ]
        .filter(Boolean)
        .join(" ");
    return `
        <article class="kanban-card ${cardClasses}" data-card-id="${card.id}" style="--card-accent:${type.color}">
            ${viewActions}
            <div class="card-type-label">${escapeHtml(type.label)}</div>
            <div class="card-title">${escapeHtml(card.title)}</div>
            <div class="card-meta">
                ${card.comment_count ? `<span>💬 ${card.comment_count}</span>` : ""}
                ${card.checklist_total ? `<span>☑ ${card.checklist_done}/${card.checklist_total}</span>` : ""}
            </div>
        </article>
    `;
}

function handleBoardPageClick(event) {
    if (!event.target.closest(".board-page")) {
        return;
    }

    const starBtn = event.target.closest("[data-action='toggle-star']");
    if (starBtn) {
        event.preventDefault();
        event.stopPropagation();
        toggleBoardStar(starBtn.dataset.boardId);
        renderBoardPage();
        if (state.boardHub.scope === "starred" && !isBoardStarred(starBtn.dataset.boardId)) {
            showSuccess("已取消星标");
        } else {
            showSuccess(isBoardStarred(starBtn.dataset.boardId) ? "已加入星标看板" : "已取消星标");
        }
        return;
    }

    const addListBtn = event.target.closest("[data-action='add-list']");
    if (addListBtn) {
        event.preventDefault();
        event.stopPropagation();
        promptCreateList();
        return;
    }

    const addCardBtn = event.target.closest("[data-action='add-card']");
    if (addCardBtn) {
        event.preventDefault();
        event.stopPropagation();
        promptCreateCard(addCardBtn.dataset.listId);
        return;
    }

    const toggleListMenuBtn = event.target.closest("[data-action='toggle-list-menu']");
    if (toggleListMenuBtn) {
        event.preventDefault();
        event.stopPropagation();
        toggleListMenu(toggleListMenuBtn.dataset.listId);
        return;
    }

    const renameListBtn = event.target.closest("[data-action='rename-list']");
    if (renameListBtn) {
        event.preventDefault();
        event.stopPropagation();
        closeAllListMenus();
        promptRenameList(renameListBtn.dataset.listId);
        return;
    }

    const deleteListBtn = event.target.closest("[data-action='delete-list']");
    if (deleteListBtn) {
        event.preventDefault();
        event.stopPropagation();
        closeAllListMenus();
        promptDeleteList(deleteListBtn.dataset.listId);
        return;
    }

    const viewActionBtn = event.target.closest("[data-card-view-action]");
    if (viewActionBtn) {
        event.preventDefault();
        event.stopPropagation();
        const cardNode = viewActionBtn.closest(".kanban-card");
        if (cardNode) {
            handleCardViewAction(viewActionBtn.dataset.cardViewAction, cardNode.dataset.cardId);
        }
        return;
    }

    const cardNode = event.target.closest(".kanban-card");
    if (cardNode && event.target.closest("#kanbanBoard")) {
        if (isEditorBoardView()) {
            openCardForBoardView(cardNode.dataset.cardId);
            return;
        }
        openCardModal(cardNode.dataset.cardId);
    }
}

function openQuickCreateDialog({ title, placeholder, defaultValue = "", onSubmit }) {
    quickCreateTitleEl.textContent = title;
    quickCreateInput.placeholder = placeholder;
    quickCreateInput.value = defaultValue;
    quickCreateSubmitHandler = onSubmit;
    quickCreateModal.show();
}

async function submitQuickCreate() {
    const value = quickCreateInput.value.trim();
    if (!value || !quickCreateSubmitHandler) {
        return;
    }
    try {
        await quickCreateSubmitHandler(value);
        quickCreateSubmitHandler = null;
        quickCreateModal.hide();
    } catch (error) {
        showError(error.message || "操作失败");
    }
}

function initSortables() {
    document.querySelectorAll(".list-cards").forEach((container) => {
        const sortable = Sortable.create(container, {
            group: "kanban-cards",
            animation: 150,
            ghostClass: "sortable-ghost",
            dragClass: "sortable-drag",
            onEnd: async (event) => {
                const cardId = event.item.dataset.cardId;
                const targetListId = event.to.dataset.listId;
                const position = event.newIndex;
                try {
                    await api(`/api/boards/${state.currentBoardId}/cards/${cardId}/move`, {
                        method: "POST",
                        body: JSON.stringify({ list_id: targetListId, position }),
                    });
                    await openBoard(state.currentBoardId);
                } catch (error) {
                    showError(error.message || "移动卡片失败");
                    await openBoard(state.currentBoardId);
                }
            },
        });
        state.sortables.push(sortable);
    });

    const boardEl = document.getElementById("kanbanBoard");
    if (boardEl) {
        const listSortable = Sortable.create(boardEl, {
            animation: 150,
            draggable: ".kanban-list",
            handle: ".list-header",
            filter: ".list-footer, .add-card-btn, .list-cards, .kanban-card, .add-list-column, .add-list-btn",
            preventOnFilter: false,
            onEnd: async (event) => {
                const orderedIds = [...boardEl.querySelectorAll(".kanban-list")].map((node) => node.dataset.listId);
                try {
                    await api(`/api/boards/${state.currentBoardId}/lists/reorder`, {
                        method: "POST",
                        body: JSON.stringify({ ordered_ids: orderedIds }),
                    });
                } catch (error) {
                    showError(error.message || "调整列表顺序失败");
                    await openBoard(state.currentBoardId);
                }
            },
        });
        state.sortables.push(listSortable);
    }
}

function destroySortables() {
    state.sortables.forEach((item) => item.destroy());
    state.sortables = [];
}

function promptCreateList() {
    openQuickCreateDialog({
        title: "添加列表",
        placeholder: "请输入列表名称",
        onSubmit: async (title) => {
            await api(`/api/boards/${state.currentBoardId}/lists`, {
                method: "POST",
                body: JSON.stringify({ title }),
            });
            showSuccess("列表已创建");
            await openBoard(state.currentBoardId);
        },
    });
}

function closeAllListMenus() {
    document.querySelectorAll(".list-menu-panel.show").forEach((node) => node.classList.remove("show"));
}

function toggleListMenu(listId) {
    const panel = document.querySelector(`[data-list-menu="${listId}"]`);
    if (!panel) {
        return;
    }
    const willShow = !panel.classList.contains("show");
    closeAllListMenus();
    if (willShow) {
        panel.classList.add("show");
    }
}

function findList(listId) {
    return state.currentBoard?.lists.find((item) => String(item.id) === String(listId)) || null;
}

function openConfirmDeleteDialog({ title, message, onSubmit }) {
    confirmDeleteTitleEl.textContent = title;
    confirmDeleteMessageEl.innerHTML = message;
    confirmDeleteSubmitHandler = onSubmit;
    confirmDeleteModal.show();
}

async function submitConfirmDelete() {
    if (!confirmDeleteSubmitHandler) {
        return;
    }
    const submitBtn = document.getElementById("confirmDeleteSubmitBtn");
    submitBtn.disabled = true;
    try {
        await confirmDeleteSubmitHandler();
        confirmDeleteSubmitHandler = null;
        confirmDeleteModal.hide();
    } catch (error) {
        showError(error.message || "操作失败");
    } finally {
        submitBtn.disabled = false;
    }
}

function promptRenameList(listId) {
    const list = findList(listId);
    openQuickCreateDialog({
        title: "重命名列表",
        placeholder: "请输入新的列表名称",
        defaultValue: list?.title || "",
        onSubmit: async (title) => {
            await api(`/api/boards/${state.currentBoardId}/lists/${listId}`, {
                method: "PATCH",
                body: JSON.stringify({ title }),
            });
            showSuccess("列表已更新");
            await openBoard(state.currentBoardId);
        },
    });
}

function promptDeleteList(listId) {
    const list = findList(listId);
    if (!list) {
        return;
    }
    const cardCount = list.cards?.length || 0;
    const cardHint =
        cardCount > 0
            ? `该列表下的 <strong>${cardCount}</strong> 张卡片将一并删除。`
            : "该列表当前没有卡片。";
    openConfirmDeleteDialog({
        title: "删除列表",
        message: `确定要删除列表 <strong>${escapeHtml(list.title)}</strong> 吗？${cardHint}`,
        onSubmit: async () => {
            await api(`/api/boards/${state.currentBoardId}/lists/${listId}`, {
                method: "DELETE",
            });
            showSuccess("列表已删除");
            await openBoard(state.currentBoardId);
        },
    });
}

function promptCreateCard(listId) {
    openQuickCreateDialog({
        title: "添加卡片",
        placeholder: "请输入卡片标题",
        onSubmit: async (title) => {
            await api(`/api/boards/${state.currentBoardId}/lists/${listId}/cards`, {
                method: "POST",
                body: JSON.stringify({ title, type: "user_story" }),
            });
            showSuccess("卡片已创建");
            await openBoard(state.currentBoardId);
        },
    });
}

function findCard(cardId) {
    for (const list of state.currentBoard.lists) {
        const card = list.cards.find((item) => String(item.id) === String(cardId));
        if (card) {
            return card;
        }
    }
    return null;
}

function openCardModal(cardId) {
    const card = findCard(cardId);
    if (!card) {
        return;
    }
    state.editingCard = card;
    state.editingChecklistIndex = null;
    state.checklistEditBackup = "";
    cardTypeSelect.value = card.type || "user_story";
    cardTitleInput.value = card.title || "";
    pendingDescriptionContent = card.description || "";
    pendingDescriptionMode = resolveCardDescriptionMode(card);
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = pendingDescriptionMode;
    }
    if (pendingDescriptionMode === "markdown") {
        if (cardDescriptionMarkdownInput) {
            cardDescriptionMarkdownInput.value = pendingDescriptionContent;
        }
        applyDescriptionModeUI("markdown");
        syncMarkdownPreview();
    } else {
        applyDescriptionModeUI("richtext");
    }
    renderChecklist(card.checklist || []);
    renderComments(card.comments || []);
    commentInput.value = "";
    cardModal.show();
    requestAnimationFrame(() => {
        if (pendingDescriptionMode === "richtext") {
            mountCardDescriptionEditor();
        }
    });
}

function getEditingChecklist() {
    return state.editingCard?.checklist || [];
}

function setEditingChecklist(items) {
    if (state.editingCard) {
        state.editingCard.checklist = items;
    }
}

function renderChecklist(items) {
    if (state.editingCard) {
        state.editingCard.checklist = items;
    }

    if (!items.length && state.editingChecklistIndex === null) {
        checklistContainer.innerHTML = `<p class="text-muted mb-0">暂无检查项</p>`;
        return;
    }

    checklistContainer.innerHTML = items
        .map((item, index) => {
            if (state.editingChecklistIndex === index) {
                return `
                    <div class="checklist-item checklist-item-editing" data-checklist-index="${index}">
                        <div class="checklist-edit-form">
                            <input class="form-control form-control-sm" type="text" value="${escapeHtml(item.text)}" placeholder="输入检查项内容">
                            <div class="checklist-edit-actions">
                                <button class="btn btn-sm btn-primary" data-action="save-checklist" data-checklist-index="${index}" type="button">保存</button>
                                <button class="btn btn-sm btn-outline-secondary" data-action="cancel-checklist" data-checklist-index="${index}" type="button">取消</button>
                                <button class="btn btn-sm btn-outline-danger" data-action="delete-checklist" data-checklist-index="${index}" type="button">删除</button>
                            </div>
                        </div>
                    </div>
                `;
            }

            return `
                <div class="checklist-item" data-checklist-index="${index}">
                    <label class="checklist-item-row">
                        <input type="checkbox" data-action="toggle-checklist" data-checklist-index="${index}" ${item.done ? "checked" : ""}>
                        <span class="checklist-item-text ${item.done ? "done" : ""}" data-action="edit-checklist" data-checklist-index="${index}" title="点击编辑">${escapeHtml(item.text) || "（空检查项）"}</span>
                    </label>
                </div>
            `;
        })
        .join("");

    bindChecklistActions();
}

function bindChecklistActions() {
    checklistContainer.querySelectorAll("[data-action='toggle-checklist']").forEach((input) => {
        input.addEventListener("change", () => {
            toggleChecklistItem(Number(input.dataset.checklistIndex), input.checked);
        });
    });
    checklistContainer.querySelectorAll("[data-action='edit-checklist']").forEach((node) => {
        node.addEventListener("click", (event) => {
            event.preventDefault();
            event.stopPropagation();
            startEditChecklistItem(Number(node.dataset.checklistIndex));
        });
    });
    checklistContainer.querySelectorAll("[data-action='save-checklist']").forEach((button) => {
        button.addEventListener("click", () => {
            const index = Number(button.dataset.checklistIndex);
            const input = checklistContainer.querySelector(
                `.checklist-item-editing[data-checklist-index="${index}"] input[type="text"]`
            );
            saveChecklistItemEdit(index, input?.value || "");
        });
    });
    checklistContainer.querySelectorAll("[data-action='cancel-checklist']").forEach((button) => {
        button.addEventListener("click", () => {
            cancelChecklistItemEdit(Number(button.dataset.checklistIndex));
        });
    });
    checklistContainer.querySelectorAll("[data-action='delete-checklist']").forEach((button) => {
        button.addEventListener("click", () => {
            deleteChecklistItem(Number(button.dataset.checklistIndex));
        });
    });

    const editingInput = checklistContainer.querySelector(".checklist-item-editing input[type='text']");
    if (editingInput) {
        editingInput.focus();
        editingInput.setSelectionRange(editingInput.value.length, editingInput.value.length);
        editingInput.addEventListener("keydown", (event) => {
            const index = state.editingChecklistIndex;
            if (index === null) {
                return;
            }
            if (event.key === "Enter") {
                event.preventDefault();
                saveChecklistItemEdit(index, editingInput.value);
            }
            if (event.key === "Escape") {
                event.preventDefault();
                cancelChecklistItemEdit(index);
            }
        });
    }
}

function startEditChecklistItem(index) {
    let nextIndex = index;
    if (state.editingChecklistIndex !== null && state.editingChecklistIndex !== index) {
        const oldIndex = state.editingChecklistIndex;
        const items = getEditingChecklist().slice();
        const backup = state.checklistEditBackup ?? "";
        const wasEmpty = !backup.trim() && !(items[oldIndex]?.text || "").trim();
        if (wasEmpty) {
            items.splice(oldIndex, 1);
            if (oldIndex < nextIndex) {
                nextIndex -= 1;
            }
        } else if (items[oldIndex]) {
            items[oldIndex] = { ...items[oldIndex], text: backup };
        }
        state.editingChecklistIndex = null;
        state.checklistEditBackup = "";
        setEditingChecklist(items);
    }

    const items = getEditingChecklist();
    const item = items[nextIndex];
    if (!item) {
        return;
    }
    state.editingChecklistIndex = nextIndex;
    state.checklistEditBackup = item.text || "";
    renderChecklist(items);
}

function saveChecklistItemEdit(index, text) {
    const nextText = text.trim();
    if (!nextText) {
        showError("检查项内容不能为空");
        return false;
    }

    const items = getEditingChecklist().slice();
    if (!items[index]) {
        return false;
    }

    items[index] = { ...items[index], text: nextText };
    state.editingChecklistIndex = null;
    state.checklistEditBackup = "";
    setEditingChecklist(items);
    renderChecklist(items);
    return true;
}

function cancelChecklistItemEdit(index) {
    const items = getEditingChecklist().slice();
    const backup = state.checklistEditBackup ?? items[index]?.text ?? "";

    if (!backup.trim()) {
        items.splice(index, 1);
    } else if (items[index]) {
        items[index] = { ...items[index], text: backup };
    }

    state.editingChecklistIndex = null;
    state.checklistEditBackup = "";
    setEditingChecklist(items);
    renderChecklist(items);
}

function deleteChecklistItem(index) {
    const items = getEditingChecklist().slice();
    if (!items[index]) {
        return;
    }
    items.splice(index, 1);
    state.editingChecklistIndex = null;
    state.checklistEditBackup = "";
    setEditingChecklist(items);
    renderChecklist(items);
}

function toggleChecklistItem(index, done) {
    const items = getEditingChecklist().slice();
    if (!items[index]) {
        return;
    }
    items[index] = { ...items[index], done };
    setEditingChecklist(items);
    renderChecklist(items);
}

function flushChecklistEditIfNeeded() {
    if (state.editingChecklistIndex === null) {
        return true;
    }
    const input = checklistContainer.querySelector(".checklist-item-editing input[type='text']");
    if (!input) {
        state.editingChecklistIndex = null;
        state.checklistEditBackup = "";
        return true;
    }
    return saveChecklistItemEdit(state.editingChecklistIndex, input.value);
}

function renderComments(comments) {
    commentsContainer.innerHTML = comments.length
        ? comments.map((item) => renderCommentItem(item, { isReply: false })).join("")
        : `<p class="text-muted mb-0">暂无评论</p>`;

    bindCommentActions();
}

function renderCommentItem(item, { isReply }) {
    const replyButton = isReply
        ? ""
        : `<button class="btn btn-sm btn-link" data-action="reply-comment" data-comment-id="${item.id}" type="button">回复</button>`;
    const repliesHtml =
        !isReply && item.replies?.length
            ? `<div class="comment-replies">${item.replies.map((reply) => renderCommentItem(reply, { isReply: true })).join("")}</div>`
            : "";
    const replyFormSlot = isReply
        ? ""
        : `<div class="comment-reply-form" data-reply-form-for="${item.id}"></div>`;

    return `
        <article class="comment-item ${isReply ? "comment-reply" : ""}" data-comment-id="${item.id}">
            <div class="comment-head">
                <div class="comment-meta">
                    <span class="comment-author">${escapeHtml(item.author || "我")}</span>
                    <span class="comment-time">${formatDateTime(item.updated_at || item.created_at)}</span>
                </div>
                <div class="comment-actions">
                    <button class="btn btn-sm btn-link" data-action="edit-comment" data-comment-id="${item.id}" type="button">编辑</button>
                    <button class="btn btn-sm btn-link text-danger" data-action="delete-comment" data-comment-id="${item.id}" data-is-reply="${isReply ? "1" : "0"}" type="button">删除</button>
                    ${replyButton}
                </div>
            </div>
            <p class="comment-content">${escapeHtml(item.content)}</p>
            ${replyFormSlot}
            ${repliesHtml}
        </article>
    `;
}

function findCommentById(commentId) {
    for (const comment of state.editingCard?.comments || []) {
        if (String(comment.id) === String(commentId)) {
            return comment;
        }
        for (const reply of comment.replies || []) {
            if (String(reply.id) === String(commentId)) {
                return reply;
            }
        }
    }
    return null;
}

function bindCommentActions() {
    commentsContainer.querySelectorAll("[data-action='delete-comment']").forEach((button) => {
        button.addEventListener("click", () => deleteComment(button.dataset.commentId, button.dataset.isReply === "1"));
    });
    commentsContainer.querySelectorAll("[data-action='edit-comment']").forEach((button) => {
        button.addEventListener("click", () => startEditComment(button.dataset.commentId));
    });
    commentsContainer.querySelectorAll("[data-action='reply-comment']").forEach((button) => {
        button.addEventListener("click", () => startReplyComment(button.dataset.commentId));
    });
}

function syncEditingCard(card) {
    state.editingCard = card;
    for (const list of state.currentBoard?.lists || []) {
        const index = list.cards.findIndex((item) => String(item.id) === String(card.id));
        if (index >= 0) {
            list.cards[index] = card;
            break;
        }
    }
}

function startEditComment(commentId) {
    const comment = findCommentById(commentId);
    if (!comment) {
        return;
    }

    const itemNode = commentsContainer.querySelector(`[data-comment-id="${commentId}"]`);
    if (!itemNode) {
        return;
    }

    itemNode.innerHTML = `
        <div class="comment-head">
            <div class="comment-meta">
                <span class="comment-author">${escapeHtml(comment.author || "我")}</span>
                <span class="comment-time">编辑评论</span>
            </div>
        </div>
        <div class="comment-edit-form">
            <textarea class="form-control" rows="3">${escapeHtml(comment.content)}</textarea>
            <div class="comment-edit-actions">
                <button class="btn btn-sm btn-primary" data-action="save-comment" data-comment-id="${commentId}" type="button">保存</button>
                <button class="btn btn-sm btn-outline-secondary" data-action="cancel-comment" type="button">取消</button>
            </div>
        </div>
    `;

    itemNode.querySelector("[data-action='save-comment']").addEventListener("click", () => {
        saveCommentEdit(commentId, itemNode.querySelector("textarea").value);
    });
    itemNode.querySelector("[data-action='cancel-comment']").addEventListener("click", () => {
        renderComments(state.editingCard.comments || []);
    });
}

function startReplyComment(commentId) {
    const comment = findCommentById(commentId);
    if (!comment) {
        return;
    }

    commentsContainer.querySelectorAll(".comment-reply-form").forEach((node) => {
        node.innerHTML = "";
    });

    const formSlot = commentsContainer.querySelector(`[data-reply-form-for="${commentId}"]`);
    if (!formSlot) {
        return;
    }

    formSlot.innerHTML = `
        <textarea class="form-control" rows="2" placeholder="回复 ${escapeHtml(comment.author || "我")}..."></textarea>
        <div class="comment-reply-form-actions">
            <button class="btn btn-sm btn-primary" data-action="submit-reply" type="button">发送回复</button>
            <button class="btn btn-sm btn-outline-secondary" data-action="cancel-reply" type="button">取消</button>
        </div>
    `;

    const textarea = formSlot.querySelector("textarea");
    textarea.focus();
    formSlot.querySelector("[data-action='submit-reply']").addEventListener("click", () => {
        submitReply(commentId, textarea.value);
    });
    formSlot.querySelector("[data-action='cancel-reply']").addEventListener("click", () => {
        formSlot.innerHTML = "";
    });
}

async function submitReply(parentCommentId, content) {
    if (!state.editingCard) {
        return;
    }
    const nextContent = content.trim();
    if (!nextContent) {
        showError("回复内容不能为空");
        return;
    }

    const result = await api(`/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}/comments`, {
        method: "POST",
        body: JSON.stringify({ content: nextContent, parent_id: parentCommentId }),
    });
    syncEditingCard(result.item);
    renderComments(result.item.comments || []);
    showSuccess("回复已发送");
}

async function saveCommentEdit(commentId, content) {
    if (!state.editingCard) {
        return;
    }
    const nextContent = content.trim();
    if (!nextContent) {
        showError("评论内容不能为空");
        return;
    }

    const result = await api(
        `/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}/comments/${commentId}`,
        {
            method: "PATCH",
            body: JSON.stringify({ content: nextContent }),
        }
    );
    syncEditingCard(result.item);
    renderComments(result.item.comments || []);
    showSuccess("评论已更新");
}

async function deleteComment(commentId, isReply = false) {
    if (!state.editingCard) {
        return;
    }
    const message = isReply ? "确定删除这条回复吗？" : "确定删除这条评论及其所有回复吗？";
    if (!confirm(message)) {
        return;
    }

    const result = await api(
        `/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}/comments/${commentId}`,
        { method: "DELETE" }
    );
    syncEditingCard(result.item);
    renderComments(result.item.comments || []);
    showSuccess(isReply ? "回复已删除" : "评论已删除");
}

function addChecklistItem() {
    if (!flushChecklistEditIfNeeded()) {
        return;
    }

    const items = getEditingChecklist().slice();
    items.push({ text: "", done: false });
    state.editingChecklistIndex = items.length - 1;
    state.checklistEditBackup = "";
    setEditingChecklist(items);
    renderChecklist(items);
}

function collectChecklistFromDom() {
    return getEditingChecklist().map((item) => ({
        text: item.text || "",
        done: Boolean(item.done),
    }));
}

async function saveCard() {
    if (!state.editingCard) {
        return;
    }
    if (!flushChecklistEditIfNeeded()) {
        return;
    }
    const descriptionPayload = collectDescriptionPayload();
    const payload = {
        title: cardTitleInput.value.trim(),
        type: cardTypeSelect.value,
        description: descriptionPayload.description,
        description_data: descriptionPayload.description_data,
        checklist: collectChecklistFromDom().filter((item) => item.text.trim()),
    };
    await api(`/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
    cardModal.hide();
    showSuccess("卡片已保存");
    await openBoard(state.currentBoardId);
}

async function deleteCurrentCard() {
    if (!state.editingCard || !confirm("确定删除该卡片吗？")) {
        return;
    }
    await api(`/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}`, {
        method: "DELETE",
    });
    cardModal.hide();
    showSuccess("卡片已删除");
    await openBoard(state.currentBoardId);
}

async function submitComment() {
    if (!state.editingCard) {
        return;
    }
    const content = commentInput.value.trim();
    if (!content) {
        return;
    }
    const result = await api(`/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}/comments`, {
        method: "POST",
        body: JSON.stringify({ content }),
    });
    syncEditingCard(result.item);
    renderComments(result.item.comments || []);
    commentInput.value = "";
    showSuccess("评论已添加");
}

async function openBoardForm(boardId = null) {
    try {
        state.settings = await api("/api/settings");
    } catch (error) {
        showError(error.message || "加载设置失败");
        return;
    }

    try {
        state.editingBoardId = boardId;
        const board = boardId ? findBoardById(boardId) : null;
        document.getElementById("boardFormTitle").textContent = board ? "编辑看板" : "新建看板";
        document.getElementById("boardTitleInput").value = board?.title || "";
        populateBoardStatusSelect(board ? resolveBoardStatus(board).id : "not_started");
        document.getElementById("boardStartInput").value = board?.start_date || "";
        document.getElementById("boardEndInput").value = board?.end_date || "";
        populateBoardOrgInput(board ? board.organization : getDefaultOrgForHub());
        boardFormModal.show();
    } catch (error) {
        showError(error.message || "打开看板表单失败");
    }
}

async function saveBoardForm() {
    const payload = {
        title: document.getElementById("boardTitleInput").value.trim(),
        status_id: boardStatusSelect.value,
        start_date: document.getElementById("boardStartInput").value,
        end_date: document.getElementById("boardEndInput").value,
        organization: normalizeBoardOrganization(getBoardOrgElements().input?.value),
    };
    if (!payload.title) {
        showError("看板名称不能为空");
        return;
    }

    try {
        if (state.editingBoardId) {
            await api(`/api/boards/${state.editingBoardId}`, {
                method: "PATCH",
                body: JSON.stringify(payload),
            });
            boardFormModal.hide();
            await loadBoards();
            showSuccess("看板已更新");
            if (state.currentBoardId && String(state.currentBoardId) === String(state.editingBoardId)) {
                await openBoard(state.currentBoardId);
            } else {
                renderBoardList();
            }
            return;
        }

        const result = await api("/api/boards", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        boardFormModal.hide();
        await loadBoards();
        const created = state.boards.find((item) => String(item.id) === String(result.item.id));
        if (!created) {
            showError("看板已提交但未写入存储，请重启服务后重试");
            renderBoardList();
            return;
        }
        showSuccess("看板已创建");
        location.hash = `#/board/${result.item.id}`;
    } catch (error) {
        showError(error.message || "保存看板失败");
    }
}

function handleSearchKeydown(event) {
    const items = [...searchResultsPanel.querySelectorAll(".search-item")];
    const activeIndex = items.findIndex((node) => node.classList.contains("active"));

    if (event.key === "Enter") {
        event.preventDefault();
        if (activeIndex >= 0 && items[activeIndex]) {
            items[activeIndex].click();
            return;
        }
        performSearch(globalSearchInput.value.trim());
        return;
    }

    if (event.key === "ArrowDown") {
        event.preventDefault();
        if (!items.length) {
            return;
        }
        const nextIndex = activeIndex < items.length - 1 ? activeIndex + 1 : 0;
        setActiveSearchItem(items, nextIndex);
        return;
    }

    if (event.key === "ArrowUp") {
        event.preventDefault();
        if (!items.length) {
            return;
        }
        const nextIndex = activeIndex > 0 ? activeIndex - 1 : items.length - 1;
        setActiveSearchItem(items, nextIndex);
        return;
    }

    if (event.key === "Escape") {
        closeSearchPanel();
    }
}

function setActiveSearchItem(items, index) {
    items.forEach((node, itemIndex) => {
        node.classList.toggle("active", itemIndex === index);
    });
    items[index]?.scrollIntoView({ block: "nearest" });
}

function closeSearchPanel() {
    searchResultsPanel.classList.remove("show");
    searchResultsPanel.innerHTML = "";
}

function getBoardTitle(boardId) {
    const board = state.boards.find((item) => String(item.id) === String(boardId));
    return board?.title || `看板 #${boardId}`;
}

function navigateToSearchResult(boardId, cardId = null) {
    closeSearchPanel();
    globalSearchInput.value = "";
    const nextHash = cardId ? `#/board/${boardId}/card/${cardId}` : `#/board/${boardId}`;
    if (location.hash === nextHash) {
        renderRoute();
        return;
    }
    location.hash = nextHash;
}

async function performSearch(keyword) {
    if (!keyword) {
        closeSearchPanel();
        return;
    }

    try {
        const data = await api(`/api/search?q=${encodeURIComponent(keyword)}`);
        const groups = data.groups || [];

        if (!groups.length) {
            searchResultsPanel.innerHTML = `
                <div class="search-group">
                    <p class="mb-0 text-muted">未找到「${escapeHtml(keyword)}」相关结果</p>
                </div>
            `;
            searchResultsPanel.classList.add("show");
            return;
        }

        searchResultsPanel.innerHTML = `
            <div class="search-summary">共 ${data.total || 0} 条匹配，分布在 ${groups.length} 个看板</div>
            ${groups
                .map(
                    (group) => `
                <div class="search-group">
                    <h4>${escapeHtml(group.board_title)}</h4>
                    ${(group.items || [])
                        .map(
                            (item) => `
                        <button
                            class="search-item"
                            data-search-board="${item.board_id}"
                            data-search-card="${item.card_id || ""}"
                            type="button"
                        >
                            <span class="search-item-title">${escapeHtml(item.title)}</span>
                            ${item.subtitle ? `<span class="search-item-sub">${escapeHtml(item.subtitle)}</span>` : ""}
                        </button>
                    `
                        )
                        .join("")}
                </div>
            `
                )
                .join("")}
        `;
        searchResultsPanel.classList.add("show");

        searchResultsPanel.querySelectorAll(".search-item").forEach((node) => {
            node.addEventListener("click", () => {
                const cardId = node.dataset.searchCard || null;
                navigateToSearchResult(node.dataset.searchBoard, cardId);
            });
        });
    } catch (error) {
        showError(error.message || "搜索失败");
    }
}

async function api(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.message || "请求失败");
    }
    return data;
}

function cleanupModalOverlay() {
    if (document.querySelector(".modal.show")) {
        return;
    }
    document.body.classList.remove("modal-open");
    document.body.style.removeProperty("overflow");
    document.body.style.removeProperty("padding-right");
    document.querySelectorAll(".modal-backdrop").forEach((node) => node.remove());
}

function showError(message) {
    errorBox.textContent = message;
    errorBox.classList.remove("d-none");
    successBox.classList.add("d-none");
}

function clearError() {
    errorBox.classList.add("d-none");
    errorBox.textContent = "";
}

function showSuccess(message) {
    successBox.textContent = message;
    successBox.classList.remove("d-none");
    errorBox.classList.add("d-none");
    window.setTimeout(() => successBox.classList.add("d-none"), 2200);
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
}

function formatDateRange(start, end) {
    if (!start && !end) {
        return "";
    }
    const startText = start ? formatDate(start) : "";
    const endText = end ? formatDate(end) : "";
    if (startText && endText) {
        return `${startText} - ${endText}`;
    }
    return startText || endText;
}

function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}

function formatDateTime(value) {
    if (!value) {
        return "";
    }
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
        return value;
    }
    return date.toLocaleString("zh-CN");
}

function debounce(fn, delay) {
    let timer = null;
    return (...args) => {
        window.clearTimeout(timer);
        timer = window.setTimeout(() => fn(...args), delay);
    };
}
