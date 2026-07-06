const state = {
    settings: { card_types: [] },
    boards: [],
    currentBoard: null,
    currentBoardId: null,
    currentBoardView: "kanban",
    currentBoardAccess: null,
    authUser: null,
    loginModalCancelable: false,
    editingCard: null,
    editingBoardId: null,
    sortables: [],
    editingChecklistIndex: null,
    checklistEditBackup: "",
    boardHub: {
        scope: "personal",
        orgName: "",
        sharedOwnerType: "",
        sharedOwnerId: "",
        sharedOrgId: "",
        sortBy: "custom",
    },
    boardHubGroups: {
        mine: true,
        projects: true,
        sharedProjects: true,
    },
    boardEditLocks: {},
};

const PERSONAL_BOARD_ORGANIZATION = "个人看板";
const BOARD_ORG_CUSTOM_VALUE = "__custom__";
const BOARD_HUB_STAR_STORAGE_KEY = "boardflow:starred-boards";

function normalizeBoardOrganization(name) {
    const value = (name || "").trim();
    return value || PERSONAL_BOARD_ORGANIZATION;
}

function formatBoardOrganization(name) {
    return normalizeBoardOrganization(name);
}

function getBoardOrgElements() {
    return ensureBoardOrgField();
}

function bindBoardOrgFormFieldOnce() {
    const select = document.getElementById("boardOrgSelect");
    if (!select || select.dataset.bound === "1") {
        return;
    }
    select.dataset.bound = "1";
    select.addEventListener("change", syncBoardOrgCustomField);
}

function ensureBoardOrgField() {
    let select = document.getElementById("boardOrgSelect");
    let customInput = document.getElementById("boardOrgCustomInput");
    if (select && customInput) {
        bindBoardOrgFormFieldOnce();
        return { select, customInput };
    }

    const modalBody = document.querySelector("#boardFormModal .modal-body");
    if (!modalBody) {
        return { select: null, customInput: null };
    }

    const legacyInput = document.getElementById("boardOrgInput");
    const legacyValue = (legacyInput?.value || "").trim();
    document.getElementById("boardOrgOptions")?.remove();

    const combo = document.createElement("div");
    combo.className = "board-org-combo";
    combo.id = "boardOrgField";
    combo.innerHTML = `
        <select id="boardOrgSelect" class="form-select"></select>
        <input
            id="boardOrgCustomInput"
            class="form-control board-org-custom-input"
            type="text"
            placeholder="输入自定义组织名称"
            autocomplete="off"
            hidden
        >
    `;

    const existingField = document.getElementById("boardOrgField");
    if (existingField) {
        existingField.replaceWith(combo);
    } else if (legacyInput) {
        legacyInput.replaceWith(combo);
    } else {
        const orgLabel = Array.from(modalBody.querySelectorAll(".field-label")).find(
            (node) => node.textContent.trim() === "所属组织"
        );
        if (orgLabel) {
            orgLabel.insertAdjacentElement("afterend", combo);
        } else {
            modalBody.appendChild(combo);
        }
    }

    select = document.getElementById("boardOrgSelect");
    customInput = document.getElementById("boardOrgCustomInput");
    if (legacyValue && customInput) {
        customInput.dataset.legacyValue = legacyValue;
    }

    bindBoardOrgFormFieldOnce();
    return { select, customInput };
}

function syncBoardOrgCustomField() {
    const { select, customInput } = ensureBoardOrgField();
    if (!select || !customInput) {
        return;
    }
    const useCustom = select.value === BOARD_ORG_CUSTOM_VALUE;
    customInput.hidden = !useCustom;
    if (useCustom) {
        customInput.focus();
    }
}

function getBoardOrgValue() {
    const { select, customInput } = ensureBoardOrgField();
    if (!select) {
        return PERSONAL_BOARD_ORGANIZATION;
    }
    if (select.value === BOARD_ORG_CUSTOM_VALUE) {
        const name = (customInput?.value || "").trim();
        return name ? normalizeBoardOrganization(name) : null;
    }
    return normalizeBoardOrganization(select.value);
}

const appView = document.getElementById("appView");
const errorBox = document.getElementById("errorBox");
const successBox = document.getElementById("successBox");
const cardModalEl = document.getElementById("cardModal");
const boardFormModalEl = document.getElementById("boardFormModal");
const quickCreateModalEl = document.getElementById("quickCreateModal");
const confirmDeleteModalEl = document.getElementById("confirmDeleteModal");
const listSettingsModalEl = document.getElementById("listSettingsModal");
const cardModal = new bootstrap.Modal(cardModalEl, { focus: false });
const boardFormModal = new bootstrap.Modal(boardFormModalEl);
const quickCreateModal = new bootstrap.Modal(quickCreateModalEl);
const confirmDeleteModal = new bootstrap.Modal(confirmDeleteModalEl);
const listSettingsModal = new bootstrap.Modal(listSettingsModalEl);
const quickCreateTitleEl = document.getElementById("quickCreateTitle");
const quickCreateInput = document.getElementById("quickCreateInput");
const confirmDeleteTitleEl = document.getElementById("confirmDeleteTitle");
const confirmDeleteMessageEl = document.getElementById("confirmDeleteMessage");
const listSettingsTitleEl = document.getElementById("listSettingsTitle");
const listSettingsTitleInput = document.getElementById("listSettingsTitleInput");
const listSettingsShowChecklist = document.getElementById("listSettingsShowChecklist");
const listSettingsShowComments = document.getElementById("listSettingsShowComments");
const loginModalEl = document.getElementById("loginModal");
const userPanelModalEl = document.getElementById("userPanelModal");
const boardShareModalEl = document.getElementById("boardShareModal");
const userFormModalEl = document.getElementById("userFormModal");
const loginModal = loginModalEl ? new bootstrap.Modal(loginModalEl, { backdrop: "static", keyboard: false }) : null;
const userPanelModal = userPanelModalEl ? new bootstrap.Modal(userPanelModalEl) : null;
const boardShareModal = boardShareModalEl ? new bootstrap.Modal(boardShareModalEl) : null;
const userFormModal = userFormModalEl ? new bootstrap.Modal(userFormModalEl) : null;
const loginUsernameInput = document.getElementById("loginUsernameInput");
const loginPasswordInput = document.getElementById("loginPasswordInput");
const userFormTitleEl = document.getElementById("userFormTitle");
const userFormUsernameWrap = document.getElementById("userFormUsernameWrap");
const userFormUsernameInput = document.getElementById("userFormUsernameInput");
const userFormDisplayNameInput = document.getElementById("userFormDisplayNameInput");
const userFormPasswordInput = document.getElementById("userFormPasswordInput");
const userFormPasswordConfirmWrap = document.getElementById("userFormPasswordConfirmWrap");
const userFormPasswordConfirmInput = document.getElementById("userFormPasswordConfirmInput");
const userFormPasswordHint = document.getElementById("userFormPasswordHint");
const userFormShowPassword = document.getElementById("userFormShowPassword");
const loginShowPassword = document.getElementById("loginShowPassword");
let editingUserFormId = null;
const confirmDeleteConfirmWrap = document.getElementById("confirmDeleteConfirmWrap");
const confirmDeleteConfirmInput = document.getElementById("confirmDeleteConfirmInput");
const confirmDeleteMathQuestionEl = document.getElementById("confirmDeleteMathQuestion");
const confirmDeleteSubmitBtn = document.getElementById("confirmDeleteSubmitBtn");
let quickCreateSubmitHandler = null;
let confirmDeleteSubmitHandler = null;
let confirmDeleteMathAnswer = null;
let editingListSettingsId = null;
let pendingDescriptionContent = null;
let pendingDescriptionMode = "markdown";
let descriptionInteractionMode = "view";

const cardDescriptionEditBtn = document.getElementById("cardDescriptionEditBtn");
const cardDescriptionViewBtn = document.getElementById("cardDescriptionViewBtn");
const cardDescriptionModePicker = document.getElementById("cardDescriptionModePicker");
const cardDescriptionModeSelect = document.getElementById("cardDescriptionModeSelect");
const cardDescriptionWrap = document.getElementById("cardDescriptionWrap");
const cardDescriptionViewPane = document.getElementById("cardDescriptionViewPane");
const cardDescriptionViewEmpty = document.getElementById("cardDescriptionViewEmpty");
const cardDescriptionViewContent = document.getElementById("cardDescriptionViewContent");
const cardDescriptionEditShell = document.getElementById("cardDescriptionEditShell");
const cardDescriptionRichtextPane = document.getElementById("cardDescriptionRichtextPane");
const cardDescriptionMarkdownPane = document.getElementById("cardDescriptionMarkdownPane");
const cardDescriptionMarkdownEditor = document.getElementById("cardDescriptionMarkdownEditor");

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
ensureBoardOrgField();
document.getElementById("createBoardNavBtn").addEventListener("click", () => {
    openBoardForm().catch((error) => showError(error.message || "打开看板表单失败"));
});
document.getElementById("quickCreateConfirmBtn").addEventListener("click", submitQuickCreate);
document.getElementById("confirmDeleteSubmitBtn").addEventListener("click", submitConfirmDelete);
document.getElementById("saveListSettingsBtn").addEventListener("click", () => {
    saveListSettings().catch((error) => showError(error.message || "保存列表设置失败"));
});
document.getElementById("navUserBtn")?.addEventListener("click", () => {
    if (!state.authUser) {
        showLoginModal();
        return;
    }
    openUserPanel();
});
document.getElementById("loginSubmitBtn")?.addEventListener("click", () => {
    submitLogin().catch((error) => showError(error.message || "登录失败"));
});
document.getElementById("logoutBtn")?.addEventListener("click", () => {
    logout().catch((error) => showError(error.message || "退出失败"));
});
document.getElementById("switchUserBtn")?.addEventListener("click", () => {
    userPanelModal?.hide();
    showLoginModal({ cancelable: true });
});
document.getElementById("loginModalCloseBtn")?.addEventListener("click", () => {
    cancelLoginModal();
});
loginModalEl?.addEventListener("hidden.bs.modal", () => {
    state.loginModalCancelable = false;
    document.getElementById("loginModalCloseBtn")?.classList.add("d-none");
});
document.getElementById("addFriendBtn")?.addEventListener("click", () => {
    addFriendByUsername().catch((error) => showError(error.message || "添加好友失败"));
});
document.getElementById("saveBoardShareBtn")?.addEventListener("click", () => {
    saveBoardShare().catch((error) => showError(error.message || "分享失败"));
});
document.getElementById("saveUserFormBtn")?.addEventListener("click", () => {
    saveUserForm().catch((error) => showError(error.message || "保存用户失败"));
});
loginPasswordInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
        event.preventDefault();
        submitLogin().catch((error) => showError(error.message || "登录失败"));
    }
});
userFormShowPassword?.addEventListener("change", () => {
    setPasswordInputsVisible([userFormPasswordInput, userFormPasswordConfirmInput], userFormShowPassword.checked);
});
loginShowPassword?.addEventListener("change", () => {
    setPasswordInputsVisible([loginPasswordInput], loginShowPassword.checked);
});
document.getElementById("deleteListFromSettingsBtn").addEventListener("click", () => {
    if (editingListSettingsId) {
        promptDeleteList(editingListSettingsId, { fromSettings: true });
    }
});
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
    return "markdown";
}

function applyDescriptionModeUI(mode) {
    const isMarkdown = mode === "markdown";
    cardDescriptionWrap?.classList.toggle("is-markdown-mode", isMarkdown);
    cardDescriptionRichtextPane?.classList.toggle("is-hidden", isMarkdown);
    cardDescriptionMarkdownPane?.classList.toggle("is-hidden", !isMarkdown);
    if (cardDescriptionRichtextPane) {
        cardDescriptionRichtextPane.hidden = isMarkdown;
    }
    if (cardDescriptionMarkdownPane) {
        cardDescriptionMarkdownPane.hidden = !isMarkdown;
    }
}

function applyDescriptionInteractionUI(mode = descriptionInteractionMode) {
    descriptionInteractionMode = mode;
    const isEdit = mode === "edit";

    cardDescriptionWrap?.classList.toggle("is-view-mode", !isEdit);
    cardDescriptionWrap?.classList.toggle("is-edit-mode", isEdit);

    cardDescriptionViewPane?.classList.toggle("is-hidden", isEdit);
    if (cardDescriptionViewPane) {
        cardDescriptionViewPane.hidden = isEdit;
    }

    cardDescriptionEditShell?.classList.toggle("is-hidden", !isEdit);
    if (cardDescriptionEditShell) {
        cardDescriptionEditShell.hidden = !isEdit;
    }

    cardDescriptionEditBtn?.classList.toggle("is-hidden", isEdit);
    if (cardDescriptionEditBtn) {
        cardDescriptionEditBtn.hidden = isEdit;
    }

    cardDescriptionViewBtn?.classList.toggle("is-hidden", !isEdit);
    if (cardDescriptionViewBtn) {
        cardDescriptionViewBtn.hidden = !isEdit;
    }

    cardDescriptionModePicker?.classList.toggle("is-hidden", !isEdit);
    if (cardDescriptionModePicker) {
        cardDescriptionModePicker.hidden = !isEdit;
    }
}

function destroyDescriptionEditors() {
    descriptionEditorMountToken += 1;
    if (typeof CardDescriptionEditor !== "undefined") {
        CardDescriptionEditor.destroy();
    }
    if (typeof CardMarkdownEditor !== "undefined") {
        CardMarkdownEditor.destroyEditor?.();
    }
}

function destroyDescriptionViewers() {
    if (typeof CardMarkdownEditor !== "undefined") {
        CardMarkdownEditor.destroyViewer?.();
    }
}

function collectCurrentDescriptionContent() {
    const mode = cardDescriptionModeSelect?.value || pendingDescriptionMode || "markdown";
    if (descriptionInteractionMode === "edit") {
        if (mode === "markdown") {
            return getCardMarkdownContent();
        }
        if (typeof CardDescriptionEditor !== "undefined") {
            return CardDescriptionEditor.getHtml?.() || "";
        }
    }
    return pendingDescriptionContent ?? "";
}

function renderDescriptionView() {
    destroyDescriptionEditors();
    destroyDescriptionViewers();

    const mode = pendingDescriptionMode;
    const content = pendingDescriptionContent ?? "";
    const hasContent = Boolean(String(content).trim());

    if (cardDescriptionViewEmpty) {
        cardDescriptionViewEmpty.hidden = hasContent;
    }
    if (!cardDescriptionViewContent) {
        return;
    }

    cardDescriptionViewContent.hidden = !hasContent;
    cardDescriptionViewContent.innerHTML = "";
    cardDescriptionViewContent.className = "card-description-view-content";

    if (!hasContent) {
        return;
    }

    if (mode === "markdown") {
        cardDescriptionViewContent.classList.add("card-description-view-content--markdown");
        if (typeof CardMarkdownEditor !== "undefined") {
            try {
                CardMarkdownEditor.mountViewer({ content });
            } catch (error) {
                showError(error.message || "Markdown 预览渲染失败");
            }
        }
        return;
    }

    cardDescriptionViewContent.classList.add("card-description-view-content--richtext");
    cardDescriptionViewContent.innerHTML = content;
}

function enterDescriptionEditMode() {
    applyDescriptionInteractionUI("edit");
    applyDescriptionModeUI(pendingDescriptionMode);
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = pendingDescriptionMode;
    }
    scheduleDescriptionEditorMount(pendingDescriptionMode);
}

function leaveDescriptionEditMode() {
    pendingDescriptionContent = collectCurrentDescriptionContent();
    pendingDescriptionMode = cardDescriptionModeSelect?.value || pendingDescriptionMode || "markdown";
    applyDescriptionInteractionUI("view");
    renderDescriptionView();
}

let descriptionEditorMountToken = 0;

function scheduleDescriptionEditorMount(mode = pendingDescriptionMode) {
    if (descriptionInteractionMode !== "edit") {
        return;
    }
    const token = ++descriptionEditorMountToken;
    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            if (token !== descriptionEditorMountToken) {
                return;
            }
            if (mode === "markdown") {
                mountCardMarkdownEditor();
            } else {
                mountCardDescriptionEditor();
            }
        });
    });
}

function mountCardMarkdownEditor() {
    if (typeof CardMarkdownEditor === "undefined") {
        showError("Markdown 编辑器脚本未加载，请 Ctrl+F5 强刷后重试");
        return;
    }
    try {
        CardMarkdownEditor.mount({ content: pendingDescriptionContent ?? "" });
        cardModal._focustrap?.deactivate?.();
    } catch (error) {
        showError(error.message || "Markdown 编辑器初始化失败");
    }
}

function destroyCardMarkdownEditor() {
    if (typeof CardMarkdownEditor !== "undefined") {
        CardMarkdownEditor.destroyEditor?.();
    }
}

function getCardMarkdownContent() {
    if (typeof CardMarkdownEditor === "undefined") {
        return "";
    }
    return CardMarkdownEditor.getMarkdown?.() || "";
}

function switchDescriptionMode(nextMode) {
    const mode = nextMode === "markdown" ? "markdown" : "richtext";
    const currentMode = cardDescriptionModeSelect?.value || pendingDescriptionMode || "markdown";

    if (mode !== currentMode) {
        if (currentMode === "richtext") {
            pendingDescriptionContent =
                typeof CardDescriptionEditor !== "undefined"
                    ? CardDescriptionEditor.getPlainText?.() || ""
                    : pendingDescriptionContent;
        } else {
            pendingDescriptionContent = getCardMarkdownContent();
        }
        destroyCardMarkdownEditor();
        if (typeof CardDescriptionEditor !== "undefined") {
            CardDescriptionEditor.destroy();
        }
    }

    pendingDescriptionMode = mode;
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = mode;
    }
    applyDescriptionModeUI(mode);
    if (descriptionInteractionMode === "edit") {
        scheduleDescriptionEditorMount(mode);
    }
}

function collectDescriptionPayload() {
    const mode = cardDescriptionModeSelect?.value || pendingDescriptionMode || "markdown";
    const description = collectCurrentDescriptionContent();
    pendingDescriptionContent = description;
    pendingDescriptionMode = mode;
    if (mode === "markdown") {
        return {
            description,
            description_data: { mode: "markdown" },
        };
    }
    return {
        description,
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

document.addEventListener(
    "focusin",
    (event) => {
        if (!cardModalEl.classList.contains("show")) {
            return;
        }
        if (event.target.closest("#cardDescriptionMarkdownPane, .card-description-markdown-host")) {
            event.stopImmediatePropagation();
        }
    },
    true
);

cardModalEl.addEventListener("shown.bs.modal", () => {
    if (!state.editingCard) {
        return;
    }
    if (descriptionInteractionMode === "edit") {
        scheduleDescriptionEditorMount(pendingDescriptionMode);
        return;
    }
    renderDescriptionView();
});
cardModalEl.addEventListener("hidden.bs.modal", () => {
    descriptionEditorMountToken += 1;
    if (typeof CardDescriptionEditor !== "undefined") {
        CardDescriptionEditor.destroy();
    }
    if (typeof CardMarkdownEditor !== "undefined") {
        CardMarkdownEditor.destroy?.();
    }
    pendingDescriptionContent = null;
    pendingDescriptionMode = "markdown";
    descriptionInteractionMode = "view";
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = "markdown";
    }
    applyDescriptionModeUI("markdown");
    applyDescriptionInteractionUI("view");
});
cardDescriptionEditBtn?.addEventListener("click", enterDescriptionEditMode);
cardDescriptionViewBtn?.addEventListener("click", leaveDescriptionEditMode);
cardDescriptionModeSelect?.addEventListener("change", () => {
    switchDescriptionMode(cardDescriptionModeSelect.value);
});
[cardModalEl, boardFormModalEl, quickCreateModalEl, confirmDeleteModalEl, listSettingsModalEl, userPanelModalEl, boardShareModalEl, userFormModalEl].forEach((modalEl) => {
    modalEl.addEventListener("hidden.bs.modal", cleanupModalOverlay);
});
confirmDeleteModalEl.addEventListener("hidden.bs.modal", () => {
    resetConfirmDeleteState();
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

async function loadAppVersion() {
    const badge = document.getElementById("appVersionBadge");
    if (!badge) {
        return;
    }
    try {
        const response = await fetch("/api/version");
        if (!response.ok) {
            return;
        }
        const payload = await response.json();
        if (payload.label) {
            badge.textContent = payload.label;
            badge.title = `BoardFlow ${payload.label}`;
        }
    } catch (_error) {
        // keep server-rendered fallback
    }
}

async function init() {
    cleanupModalOverlay();
    loadAppVersion();
    try {
        await loadAuth();
        updateNavAuth();
        if (!state.authUser) {
            showLoginModal();
            return;
        }
        await loadSettings();
        await loadBoards();
        renderRoute();
    } catch (error) {
        if (String(error.message || "").includes("登录")) {
            showLoginModal();
            return;
        }
        showError(error.message || "初始化失败");
    }
}

function updateNavAuth() {
    const settingsBtn = document.getElementById("navSettingsBtn");
    const createBtn = document.getElementById("createBoardNavBtn");
    const userBtn = document.getElementById("navUserBtn");
    const loggedIn = Boolean(state.authUser);
    if (settingsBtn) {
        settingsBtn.classList.toggle("d-none", !loggedIn);
        settingsBtn.href = getDefaultSettingsHash();
    }
    if (createBtn) {
        createBtn.classList.toggle("d-none", !loggedIn);
    }
    if (userBtn) {
        userBtn.textContent = loggedIn ? state.authUser.display_name || state.authUser.username : "用户";
    }
}

async function loadAuth() {
    try {
        const data = await api("/api/auth/me");
        state.authUser = data.user || null;
    } catch (_error) {
        state.authUser = null;
    }
}

function setPasswordInputsVisible(inputs, visible) {
    const type = visible ? "text" : "password";
    inputs.forEach((input) => {
        if (input) {
            input.type = type;
        }
    });
}

function resetPasswordVisibility(toggle, inputs) {
    if (toggle) {
        toggle.checked = false;
    }
    setPasswordInputsVisible(inputs, false);
}

function showLoginModal({ cancelable = false } = {}) {
    if (!loginModal) {
        return;
    }
    state.loginModalCancelable = cancelable;
    document.getElementById("loginModalCloseBtn")?.classList.toggle("d-none", !cancelable);
    loginUsernameInput.value = "";
    loginPasswordInput.value = "";
    resetPasswordVisibility(loginShowPassword, [loginPasswordInput]);
    loginModal.show();
    window.setTimeout(() => loginUsernameInput?.focus(), 180);
}

function cancelLoginModal() {
    if (!state.loginModalCancelable) {
        return;
    }
    loginModal?.hide();
    state.loginModalCancelable = false;
}

async function submitLogin() {
    const username = loginUsernameInput.value.trim();
    const password = loginPasswordInput.value;
    const result = await api("/api/auth/login", {
        method: "POST",
        body: JSON.stringify({ username, password }),
    });
    state.authUser = result.user;
    loginModal?.hide();
    updateNavAuth();
    await loadSettings();
    await loadBoards();
    if (location.hash === "#/login" || !location.hash) {
        location.hash = "#/home/personal";
    }
    renderRoute();
    showSuccess("登录成功");
}

async function logout() {
    await api("/api/auth/logout", { method: "POST" });
    state.authUser = null;
    state.boards = [];
    state.currentBoard = null;
    state.currentBoardId = null;
    state.currentBoardAccess = null;
    state.settings = { card_types: [], organizations: [], shared_boards: [], shared_org_index: [], board_statuses: [] };
    updateNavAuth();
}

async function openUserPanel() {
    document.getElementById("userPanelCurrentName").textContent =
        state.authUser?.display_name || state.authUser?.username || "";
    await renderFriendsList();
    userPanelModal?.show();
}

async function renderFriendsList() {
    const container = document.getElementById("friendsList");
    if (!container) {
        return;
    }
    const data = await api("/api/users/friends");
    const friends = data.items || [];
    container.innerHTML = friends.length
        ? friends
              .map(
                  (friend) => `
            <div class="friend-item">
                <span>${escapeHtml(friend.display_name || friend.username)}</span>
                <button class="btn btn-sm btn-outline-danger" data-remove-friend="${friend.user_id}" type="button">移除</button>
            </div>`
              )
              .join("")
        : `<p class="text-muted mb-0">暂无好友</p>`;
    container.querySelectorAll("[data-remove-friend]").forEach((node) => {
        node.addEventListener("click", () => {
            removeFriend(node.dataset.removeFriend).catch((error) => showError(error.message || "移除好友失败"));
        });
    });
}

async function addFriendByUsername() {
    const username = document.getElementById("friendSearchInput").value.trim();
    if (!username) {
        return;
    }
    await api("/api/users/friends", {
        method: "POST",
        body: JSON.stringify({ username }),
    });
    document.getElementById("friendSearchInput").value = "";
    await renderFriendsList();
    showSuccess("好友已添加");
}

async function removeFriend(friendUserId) {
    await api(`/api/users/friends/${friendUserId}`, { method: "DELETE" });
    await renderFriendsList();
    showSuccess("好友已移除");
}

async function openBoardShareModal() {
    if (!state.currentBoardId || state.currentBoardAccess?.shared) {
        return;
    }
    const friendsData = await api("/api/users/friends");
    const friends = friendsData.items || [];
    const select = document.getElementById("shareFriendSelect");
    select.innerHTML = friends.length
        ? friends.map((friend) => `<option value="${friend.user_id}">${escapeHtml(friend.display_name || friend.username)}</option>`).join("")
        : `<option value="">暂无好友</option>`;
    document.getElementById("sharePermissionEdit").checked = false;
    const sharesData = await api(`/api/shares?board_id=${encodeURIComponent(state.currentBoardId)}`);
    const list = document.getElementById("existingSharesList");
    const shares = sharesData.items || [];
    list.innerHTML = shares.length
        ? `<p class="field-label mt-3">已分享</p>${shares
              .map((share) => {
                  const grantee = share.grantee_user_id;
                  const perms = share.permissions || {};
                  return `<div class="share-item">${escapeHtml(grantee)} · ${perms.edit ? "可修改" : "只读"} <button class="btn btn-sm btn-outline-danger" data-delete-share="${share.id}" type="button">撤销</button></div>`;
              })
              .join("")}`
        : "";
    list.querySelectorAll("[data-delete-share]").forEach((node) => {
        node.addEventListener("click", () => {
            api(`/api/shares/${node.dataset.deleteShare}`, { method: "DELETE" })
                .then(() => openBoardShareModal())
                .catch((error) => showError(error.message || "撤销分享失败"));
        });
    });
    boardShareModal?.show();
}

async function saveBoardShare() {
    const granteeUserId = document.getElementById("shareFriendSelect").value;
    if (!granteeUserId) {
        showError("请选择好友");
        return;
    }
    await api("/api/shares", {
        method: "POST",
        body: JSON.stringify({
            board_id: state.currentBoardId,
            grantee_user_id: granteeUserId,
            permissions: {
                view: true,
                edit: document.getElementById("sharePermissionEdit").checked,
            },
        }),
    });
    boardShareModal?.hide();
    showSuccess("分享已保存");
}

function isBoardReadOnly() {
    return Boolean(state.currentBoardAccess?.shared && !state.currentBoardAccess?.permissions?.edit);
}

function renderRoute() {
    if (!state.authUser) {
        showLoginModal();
        return;
    }
    destroySortables();
    const hash = location.hash || "#/home/personal";
    if (hash === "#/login") {
        showLoginModal();
        return;
    }
    const boardMatch = hash.match(/^#\/board\/(\d+)(?:\/card\/([^/]+))?/);
    if (boardMatch) {
        const query = hash.includes("?") ? hash.split("?")[1] : "";
        const params = new URLSearchParams(query);
        openBoard(
            boardMatch[1],
            boardMatch[2] || null,
            params.get("owner_tenant_type"),
            params.get("owner_tenant_id")
        );
        return;
    }
    if (hash === "#/settings" || hash.startsWith("#/settings/")) {
        const activeTab = resolveSettingsTab(hash);
        const targetHash = `#/settings/${activeTab}`;
        const normalized = hash.split("?")[0];
        if (normalized !== targetHash) {
            history.replaceState(null, "", targetHash);
        }
        renderSettingsPage(activeTab);
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
    const sharedOrgOwnerMatch = normalized.match(/^#\/home\/shared-org\/([^/]+)\/([^/]+)\/(.+)$/);
    const sharedOrgMatch = normalized.match(/^#\/home\/shared-org\/(.+)$/);
    const sharedMatch = normalized.match(/^#\/home\/shared\/([^/]+)\/([^/]+)\/([^/]+)(?:\/(.+))?$/);
    const orgMatch = normalized.match(/^#\/home\/org\/(.+)$/);

    if (sharedOrgOwnerMatch) {
        state.boardHub.scope = "shared-org";
        state.boardHub.sharedOwnerType = decodeURIComponent(sharedOrgOwnerMatch[1]);
        state.boardHub.sharedOwnerId = decodeURIComponent(sharedOrgOwnerMatch[2]);
        state.boardHub.orgName = decodeURIComponent(sharedOrgOwnerMatch[3]);
        state.boardHub.sharedOrgId = "";
        return;
    }
    if (sharedOrgMatch) {
        state.boardHub.scope = "shared-org";
        state.boardHub.orgName = decodeURIComponent(sharedOrgMatch[1]);
        state.boardHub.sharedOwnerType = "";
        state.boardHub.sharedOwnerId = "";
        state.boardHub.sharedOrgId = "";
        return;
    }
    if (sharedMatch) {
        state.boardHub.scope = "shared-org";
        state.boardHub.sharedOwnerType = decodeURIComponent(sharedMatch[1]);
        state.boardHub.sharedOwnerId = decodeURIComponent(sharedMatch[2]);
        const third = decodeURIComponent(sharedMatch[3]);
        const fourth = sharedMatch[4] ? decodeURIComponent(sharedMatch[4]) : "";
        if (third.startsWith("org_")) {
            state.boardHub.sharedOrgId = third;
            state.boardHub.orgName = fourth || third;
        } else {
            state.boardHub.sharedOrgId = "";
            state.boardHub.orgName = third;
        }
        return;
    }
    if (orgMatch) {
        state.boardHub.scope = "org";
        state.boardHub.orgName = decodeURIComponent(orgMatch[1]);
        state.boardHub.sharedOwnerType = "";
        state.boardHub.sharedOwnerId = "";
        state.boardHub.sharedOrgId = "";
        return;
    }
    if (normalized === "#/home/workbench") {
        state.boardHub.scope = "workbench";
        state.boardHub.orgName = "";
        state.boardHub.sharedOwnerType = "";
        state.boardHub.sharedOwnerId = "";
        state.boardHub.sharedOrgId = "";
        return;
    }
    if (normalized === "#/home/mindmap") {
        history.replaceState(null, "", "#/home/personal");
    }
    if (normalized === "#/home/starred") {
        state.boardHub.scope = "starred";
        state.boardHub.orgName = "";
        state.boardHub.sharedOwnerType = "";
        state.boardHub.sharedOwnerId = "";
        state.boardHub.sharedOrgId = "";
        return;
    }
    if (normalized === "#/home/list" || normalized === "#/home" || normalized === "#/home/") {
        history.replaceState(null, "", "#/home/personal");
    }
    state.boardHub.scope = "personal";
    state.boardHub.orgName = "";
    state.boardHub.sharedOwnerType = "";
    state.boardHub.sharedOwnerId = "";
    state.boardHub.sharedOrgId = "";
}

function buildBoardHubHref(scope, orgName = "", sharedMeta = null) {
    if (scope === "shared-org") {
        const meta = sharedMeta || {};
        const label = orgName || meta.orgName || "";
        if (meta.ownerTenantType && meta.ownerTenantId) {
            return `#/home/shared-org/${encodeURIComponent(meta.ownerTenantType)}/${encodeURIComponent(meta.ownerTenantId)}/${encodeURIComponent(label)}`;
        }
        return `#/home/shared-org/${encodeURIComponent(label)}`;
    }
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
    if (state.boardHub.scope === "shared-org") {
        return buildBoardHubHref("shared-org", state.boardHub.orgName, {
            ownerTenantType: state.boardHub.sharedOwnerType,
            ownerTenantId: state.boardHub.sharedOwnerId,
            orgName: state.boardHub.orgName,
        });
    }
    return buildBoardHubHref(state.boardHub.scope, state.boardHub.orgName);
}

function getBoardHubTitle(hub = state.boardHub) {
    if (hub.scope === "workbench") {
        return "工作台";
    }
    if (hub.scope === "starred") {
        return "星标看板";
    }
    if (hub.scope === "shared-org") {
        const group = findSharedOrganizationNavGroup(hub);
        if (group) {
            return formatSharedOrgNavLabel(group);
        }
        return hub.orgName || "共享项目";
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

function syncBoardHubForOrganization(orgName) {
    const organization = normalizeBoardOrganization(orgName);
    state.boardHub.sharedOwnerType = "";
    state.boardHub.sharedOwnerId = "";
    state.boardHub.sharedOrgId = "";
    if (organization === PERSONAL_BOARD_ORGANIZATION) {
        state.boardHub.scope = "personal";
        state.boardHub.orgName = "";
        return;
    }
    state.boardHub.scope = "org";
    state.boardHub.orgName = organization;
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
        return boards.filter((board) => !board.shared);
    }
    if (hub.scope === "starred") {
        const starred = new Set(getStarredBoardIds());
        return boards.filter((board) => starred.has(String(board.id)));
    }
    if (hub.scope === "shared-org") {
        const orgName = normalizeBoardOrganization(hub.orgName);
        return boards.filter((board) => {
            if (!board.shared) {
                return false;
            }
            if (normalizeBoardOrganization(board.organization) !== orgName) {
                return false;
            }
            if (hub.sharedOwnerType && hub.sharedOwnerId) {
                return (
                    String(board.owner_tenant_type || "") === String(hub.sharedOwnerType) &&
                    String(board.owner_tenant_id || "") === String(hub.sharedOwnerId)
                );
            }
            return true;
        });
    }
    if (hub.scope === "org") {
        const orgName = normalizeBoardOrganization(hub.orgName);
        return boards.filter(
            (board) => !board.shared && normalizeBoardOrganization(board.organization) === orgName
        );
    }
    return boards.filter(
        (board) =>
            !board.shared && normalizeBoardOrganization(board.organization) === PERSONAL_BOARD_ORGANIZATION
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
    let organizations;
    if (state.authUser?.is_super_admin) {
        organizations = copyOrganizationList(
            state.settings.organizations || state.currentBoard?.settings?.organizations || []
        );
    } else {
        organizations = copyOrganizationList(state.settings.organizations || []);
    }

    const seen = new Set(
        organizations.map((item) => (item.name || "").trim()).filter(Boolean)
    );
    for (const board of state.boards || []) {
        if (board.shared) {
            continue;
        }
        const name = (board.organization || "").trim();
        if (!name || name === PERSONAL_BOARD_ORGANIZATION || seen.has(name)) {
            continue;
        }
        seen.add(name);
        organizations.push({ id: "", name, note: "" });
    }

    return organizations.sort((left, right) =>
        (left.name || "").localeCompare(right.name || "", "zh-CN")
    );
}

function copyOrganizationList(items) {
    return (items || []).map((item) => ({ ...item }));
}

function getSharedBoards() {
    return state.settings.shared_boards || [];
}

function getSharedOrgIndex() {
    return state.settings.shared_org_index || [];
}

function getSharedOrganizationNavGroups() {
    return groupSharedBoardsForNav();
}

function formatSharedOrgNavLabel(group) {
    const orgName = normalizeBoardOrganization(group.org_name || group.organization);
    const ownerName = (group.owner_display_name || "").trim() || "未知用户";
    return `${orgName} (${ownerName})`;
}

function findSharedOrganizationNavGroup(hub = state.boardHub) {
    const orgName = normalizeBoardOrganization(hub.orgName);
    const groups = getSharedOrganizationNavGroups();
    if (hub.sharedOwnerType && hub.sharedOwnerId) {
        return groups.find(
            (group) =>
                normalizeBoardOrganization(group.org_name) === orgName &&
                String(group.owner_tenant_type || "") === String(hub.sharedOwnerType) &&
                String(group.owner_tenant_id || "") === String(hub.sharedOwnerId)
        );
    }
    return groups.find((group) => normalizeBoardOrganization(group.org_name) === orgName);
}

function isSharedOrganizationNavActive(group, hub = state.boardHub) {
    return (
        hub.scope === "shared-org" &&
        normalizeBoardOrganization(hub.orgName) === normalizeBoardOrganization(group.org_name) &&
        String(hub.sharedOwnerType || "") === String(group.owner_tenant_type || "") &&
        String(hub.sharedOwnerId || "") === String(group.owner_tenant_id || "")
    );
}

function getSharedOrganizationNames() {
    return getSharedOrganizationNavGroups().map((group) => formatSharedOrgNavLabel(group));
}

function groupSharedBoardsForNav(boards = getSharedBoards()) {
    const grouped = new Map();
    for (const item of boards) {
        const orgName = normalizeBoardOrganization(item.organization);
        const key = `${item.owner_tenant_type}:${item.owner_tenant_id}:${orgName}`;
        if (!grouped.has(key)) {
            grouped.set(key, {
                owner_tenant_type: item.owner_tenant_type,
                owner_tenant_id: item.owner_tenant_id,
                org_name: orgName,
                owner_display_name: item.owner_display_name || "",
                board_ids: [],
                boards: [],
            });
        }
        const group = grouped.get(key);
        const boardId = String(item.board_id || "");
        if (boardId && !group.board_ids.includes(boardId)) {
            group.board_ids.push(boardId);
        }
        group.boards.push(item);
    }
    return Array.from(grouped.values()).sort((left, right) => {
        const leftLabel = `${left.org_name} ${left.owner_display_name}`;
        const rightLabel = `${right.org_name} ${right.owner_display_name}`;
        return leftLabel.localeCompare(rightLabel, "zh-CN");
    });
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
    const { select, customInput } = ensureBoardOrgField();
    if (!select || !customInput) {
        throw new Error("看板表单组件缺失，请刷新页面后重试");
    }

    const legacyValue = (customInput.dataset.legacyValue || "").trim();
    delete customInput.dataset.legacyValue;
    const current = normalizeBoardOrganization(selectedName || legacyValue);
    const organizations = getOrganizations();
    const seen = new Set();
    const options = [];

    function addOption(value, label = value) {
        const name = (value || "").trim();
        if (!name || seen.has(name)) {
            return;
        }
        seen.add(name);
        options.push(`<option value="${escapeHtml(name)}">${escapeHtml(label)}</option>`);
    }

    addOption(PERSONAL_BOARD_ORGANIZATION);
    organizations.forEach((item) => addOption(item.name));
    options.push(`<option value="${BOARD_ORG_CUSTOM_VALUE}">自定义名称…</option>`);

    select.innerHTML = options.join("");

    if (seen.has(current)) {
        select.value = current;
        customInput.value = "";
        customInput.hidden = true;
        return;
    }

    select.value = BOARD_ORG_CUSTOM_VALUE;
    customInput.value = current;
    customInput.hidden = false;
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

function findBoardById(boardId, ownerTenantType = null, ownerTenantId = null) {
    if (ownerTenantType && ownerTenantId) {
        const sharedMatch = state.boards.find(
            (item) =>
                String(item.id) === String(boardId) &&
                item.shared &&
                String(item.owner_tenant_type) === String(ownerTenantType) &&
                String(item.owner_tenant_id) === String(ownerTenantId)
        );
        if (sharedMatch) {
            return sharedMatch;
        }
    }
    const fromList = state.boards.find(
        (item) => String(item.id) === String(boardId) && !item.shared
    );
    if (fromList) {
        return fromList;
    }
    const fallback = state.boards.find((item) => String(item.id) === String(boardId));
    if (fallback) {
        return fallback;
    }
    if (state.currentBoard?.board && String(state.currentBoard.board.id) === String(boardId)) {
        return state.currentBoard.board;
    }
    return null;
}

function buildBoardHref(board) {
    if (board?.shared && board.owner_tenant_type && board.owner_tenant_id) {
        return `#/board/${board.id}?owner_tenant_type=${encodeURIComponent(board.owner_tenant_type)}&owner_tenant_id=${encodeURIComponent(board.owner_tenant_id)}`;
    }
    return `#/board/${board.id}`;
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
    { id: "stkaiti", label: "华文楷体", stack: 'STKaiti, "Kaiti SC", KaiTi, serif' },
    { id: "stxingkai", label: "华文行楷", stack: 'STXingkai, "Xingkai SC", cursive' },
    { id: "simli", label: "隶书", stack: 'SimLi, "LiSu", serif' },
    { id: "youyuan", label: "幼圆", stack: 'YouYuan, "Yuanti SC", sans-serif' },
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
        desc: "看板页标题与首页看板卡片名称（「看板标题：」前缀固定白色，不受此项影响）",
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
    { id: "statuses", label: "看板状态", hash: "#/settings/statuses", icon: "◉", adminOnly: true },
    { id: "organizations", label: "所属组织", hash: "#/settings/organizations", icon: "▤", adminOnly: true },
    { id: "my-organizations", label: "所属组织", hash: "#/settings/my-organizations", icon: "▤", userOnly: true },
    { id: "user-board-transfer", label: "看板导入导出", hash: "#/settings/board-transfer", icon: "⇄", userOnly: true },
    { id: "fonts", label: "字体", hash: "#/settings/fonts", icon: "A", adminOnly: true },
    { id: "collaboration", label: "协作锁", hash: "#/settings/collaboration", icon: "🔒", adminOnly: true },
    { id: "users", label: "用户管理", hash: "#/settings/users", icon: "👤", adminOnly: true },
    { id: "data-transfer", label: "导入导出", hash: "#/settings/data-transfer", icon: "⇅", adminOnly: true },
    { id: "board-compare", label: "多平台对比", hash: "#/settings/board-compare", icon: "⇄", adminOnly: true },
];

function getDefaultSettingsTab() {
    return state.authUser?.is_super_admin ? "statuses" : "my-organizations";
}

function getDefaultSettingsHash() {
    return `#/settings/${getDefaultSettingsTab()}`;
}

function getVisibleSettingsTabs() {
    const isAdmin = Boolean(state.authUser?.is_super_admin);
    return SETTINGS_TABS.filter((tab) => {
        if (tab.adminOnly && !isAdmin) {
            return false;
        }
        if (tab.userOnly && isAdmin) {
            return false;
        }
        return true;
    });
}

function resolveSettingsTab(hash = location.hash) {
    const normalized = hash.split("?")[0];
    const defaultTab = getDefaultSettingsTab();
    if (normalized === "#/settings") {
        return defaultTab;
    }
    if (normalized.startsWith("#/settings/users")) {
        return "users";
    }
    if (normalized.startsWith("#/settings/organizations")) {
        return state.authUser?.is_super_admin ? "organizations" : "my-organizations";
    }
    if (normalized.startsWith("#/settings/my-organizations")) {
        return "my-organizations";
    }
    if (normalized.startsWith("#/settings/board-transfer")) {
        return "user-board-transfer";
    }
    if (normalized.startsWith("#/settings/data-transfer")) {
        return "data-transfer";
    }
    if (normalized.startsWith("#/settings/board-compare")) {
        return "board-compare";
    }
    if (normalized.startsWith("#/settings/fonts")) {
        return "fonts";
    }
    if (normalized.startsWith("#/settings/collaboration")) {
        return "collaboration";
    }
    if (normalized.startsWith("#/settings/statuses")) {
        return state.authUser?.is_super_admin ? "statuses" : defaultTab;
    }
    return defaultTab;
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
                ${getVisibleSettingsTabs()
                    .map(
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
                )
                    .join("")}
            </nav>
        </aside>
    `;
}

function renderUsersSettingsPanel(users = []) {
    return `
        <section class="settings-panel">
            <div class="settings-panel-head">
                <div>
                    <h2>用户管理</h2>
                    <p class="text-muted">创建和管理系统登录用户（超级管理员不在此列表中）。</p>
                </div>
                <button class="btn btn-primary" id="createUserBtn" type="button">添加用户</button>
            </div>
            <div class="users-settings-list">
                ${
                    users.length
                        ? users
                              .map(
                                  (user) => `
                        <div class="users-settings-item" data-user-id="${user.id}">
                            <div>
                                <strong>${escapeHtml(user.display_name || user.username)}</strong>
                                <div class="text-muted">${escapeHtml(user.username)} · ${user.status === "disabled" ? "已禁用" : "正常"}</div>
                            </div>
                            <div class="users-settings-actions">
                                <button class="btn btn-sm btn-light" data-action="edit-user" data-user-id="${user.id}" type="button">编辑</button>
                                <button class="btn btn-sm btn-outline-danger" data-action="delete-user" data-user-id="${user.id}" type="button">删除</button>
                            </div>
                        </div>`
                              )
                              .join("")
                        : `<p class="text-muted mb-0">暂无用户，点击右上角添加。</p>`
                }
            </div>
        </section>
    `;
}

function bindUsersSettingsPanel() {
    document.getElementById("createUserBtn")?.addEventListener("click", () => {
        openUserFormDialog().catch((error) => showError(error.message || "打开用户表单失败"));
    });
    document.querySelectorAll("[data-action='edit-user']").forEach((node) => {
        node.addEventListener("click", () => {
            openUserFormDialog(node.dataset.userId).catch((error) => showError(error.message || "打开用户表单失败"));
        });
    });
    document.querySelectorAll("[data-action='delete-user']").forEach((node) => {
        node.addEventListener("click", () => {
            promptDeleteUser(node.dataset.userId);
        });
    });
}

async function openUserFormDialog(userId = null) {
    const usersData = await api("/api/users");
    const existing = userId ? usersData.items.find((item) => String(item.id) === String(userId)) : null;
    editingUserFormId = userId;
    userFormTitleEl.textContent = existing ? "编辑用户" : "添加用户";
    userFormUsernameWrap.classList.toggle("d-none", Boolean(existing));
    userFormPasswordConfirmWrap.classList.toggle("d-none", Boolean(existing));
    userFormPasswordHint.classList.toggle("d-none", !existing);
    userFormUsernameInput.value = existing?.username || "";
    userFormDisplayNameInput.value = existing?.display_name || existing?.username || "";
    userFormPasswordInput.value = "";
    userFormPasswordConfirmInput.value = "";
    resetPasswordVisibility(userFormShowPassword, [userFormPasswordInput, userFormPasswordConfirmInput]);
    userFormPasswordInput.placeholder = existing ? "留空则不修改密码" : "设置登录密码";
    userFormModal?.show();
    window.setTimeout(() => {
        (existing ? userFormDisplayNameInput : userFormUsernameInput)?.focus();
    }, 180);
}

function assertPasswordFormat(password) {
    if (password.length <= 1) {
        throw new Error("密码至少 2 个字符");
    }
    if (!/^[A-Za-z0-9]+$/.test(password)) {
        throw new Error("密码只能包含英文字母和数字");
    }
}

async function saveUserForm() {
    const displayName = userFormDisplayNameInput.value.trim();
    const password = userFormPasswordInput.value;
    const passwordConfirm = userFormPasswordConfirmInput.value;

    if (editingUserFormId) {
        const payload = {};
        if (displayName) {
            payload.display_name = displayName;
        }
        if (password) {
            assertPasswordFormat(password);
            payload.password = password;
        }
        if (!payload.display_name && !payload.password) {
            throw new Error("请修改显示名称或密码");
        }
        await api(`/api/users/${editingUserFormId}`, {
            method: "PATCH",
            body: JSON.stringify(payload),
        });
        showSuccess("用户已更新");
    } else {
        const username = userFormUsernameInput.value.trim();
        if (!username) {
            throw new Error("用户名不能为空");
        }
        if (!displayName) {
            throw new Error("显示名称不能为空");
        }
        if (!password) {
            throw new Error("密码不能为空");
        }
        assertPasswordFormat(password);
        if (password !== passwordConfirm) {
            throw new Error("两次输入的密码不一致");
        }
        await api("/api/users", {
            method: "POST",
            body: JSON.stringify({ username, display_name: displayName, password }),
        });
        showSuccess("用户已创建");
    }
    editingUserFormId = null;
    userFormModal?.hide();
    renderSettingsPage("users");
}

function promptDeleteUser(userId) {
    openConfirmDeleteDialog({
        title: "删除用户",
        message: "确定要删除该用户吗？其看板数据将一并删除。",
        onSubmit: async () => {
            await api(`/api/users/${userId}`, { method: "DELETE" });
            showSuccess("用户已删除");
            renderSettingsPage("users");
        },
    });
}

async function loadUsersForSettings() {
    const data = await api("/api/users");
    return data.items || [];
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

function getCollaborationSettings() {
    const collab = state.settings?.collaboration || {};
    return {
        enabled: collab.enabled !== false,
        card_optimistic_lock: collab.card_optimistic_lock !== false,
        editor_exclusive_lock: collab.editor_exclusive_lock !== false,
        lease_ttl_sec: Number(collab.lease_ttl_sec) || 300,
        heartbeat_interval_sec: Number(collab.heartbeat_interval_sec) || 60,
        allow_force_takeover: Boolean(collab.allow_force_takeover),
    };
}

function renderCollaborationSettingsPanel() {
    const collab = getCollaborationSettings();
    return `
        <div class="settings-panel">
            <h2>多人协作</h2>
            <p class="panel-desc">
                卡片模态框字段使用乐观锁（revision 冲突提示）；画布/脑图/表格使用独占编辑锁。
                锁租约默认 5 分钟无心跳自动释放，前端每 1 分钟续期一次。
            </p>
            <div class="row g-3">
                <div class="col-md-6">
                    <label class="form-label d-flex gap-2 align-items-center">
                        <input type="checkbox" id="collabEnabled" ${collab.enabled ? "checked" : ""}>
                        启用协作控制
                    </label>
                </div>
                <div class="col-md-6">
                    <label class="form-label d-flex gap-2 align-items-center">
                        <input type="checkbox" id="collabCardLock" ${collab.card_optimistic_lock ? "checked" : ""}>
                        卡片字段乐观锁
                    </label>
                </div>
                <div class="col-md-6">
                    <label class="form-label d-flex gap-2 align-items-center">
                        <input type="checkbox" id="collabEditorLock" ${collab.editor_exclusive_lock ? "checked" : ""}>
                        重型编辑器独占锁
                    </label>
                </div>
                <div class="col-md-6">
                    <label class="form-label" for="collabLeaseTtl">锁租约（秒）</label>
                    <input class="form-control" id="collabLeaseTtl" type="number" min="30" max="3600" value="${collab.lease_ttl_sec}">
                </div>
                <div class="col-md-6">
                    <label class="form-label" for="collabHeartbeat">心跳间隔（秒）</label>
                    <input class="form-control" id="collabHeartbeat" type="number" min="30" max="3600" value="${collab.heartbeat_interval_sec}">
                </div>
            </div>
            <div class="settings-toolbar">
                <button class="btn btn-primary" id="saveCollaborationSettingsBtn" type="button">保存协作设置</button>
            </div>
        </div>
    `;
}

function bindCollaborationSettingsPanel() {
    document.getElementById("saveCollaborationSettingsBtn")?.addEventListener("click", () => {
        saveCollaborationSettings().catch((error) => showError(error.message || "保存协作设置失败"));
    });
}

async function saveCollaborationSettings() {
    const payload = {
        enabled: document.getElementById("collabEnabled")?.checked ?? true,
        card_optimistic_lock: document.getElementById("collabCardLock")?.checked ?? true,
        editor_exclusive_lock: document.getElementById("collabEditorLock")?.checked ?? true,
        lease_ttl_sec: Number(document.getElementById("collabLeaseTtl")?.value || 300),
        heartbeat_interval_sec: Number(document.getElementById("collabHeartbeat")?.value || 60),
    };
    const result = await api("/api/settings/collaboration", {
        method: "PUT",
        body: JSON.stringify({ collaboration: payload }),
    });
    state.settings = result.settings || state.settings;
    showSuccess(result.message || "协作设置已保存");
}

function getOwnedBoards() {
    return (state.boards || []).filter((board) => !board.shared);
}

function formatBoardTransferOptionLabel(board) {
    const title = (board.title || board.id || "未命名看板").trim();
    const orgName = normalizeBoardOrganization(board.organization);
    return `${title}（${orgName}）`;
}

function renderOrgTransferSection(options = {}) {
    const {
        prefix = "ownerTransfer",
        orgDesc = "导出/导入您创建的组织下看板。导入默认合并，可选覆盖该组织下已有看板。",
    } = options;
    const organizations = getOrganizations();
    const orgOptions = [
        `<option value="org_0">${escapeHtml(PERSONAL_BOARD_ORGANIZATION)}</option>`,
        ...organizations.map(
            (org) => `<option value="${escapeHtml(org.id)}">${escapeHtml(org.name)}</option>`
        ),
    ].join("");

    return `
        <div class="transfer-section">
            <h3>组织导入导出</h3>
            <p class="transfer-desc">${orgDesc}</p>
            <div class="transfer-field-row">
                <label class="field-label" for="${prefix}ExportOrgSelect">选择组织</label>
                <select id="${prefix}ExportOrgSelect" class="form-select">${orgOptions}</select>
            </div>
            <div class="transfer-actions">
                <button class="btn btn-outline-primary" id="${prefix}ExportOrgBtn" type="button">导出组织 .dat</button>
                <label class="btn btn-outline-secondary transfer-file-btn">
                    选择组织包…
                    <input id="${prefix}ImportOrgFile" type="file" accept=".dat,application/json,text/plain" hidden>
                </label>
                <select id="${prefix}ImportOrgMode" class="form-select form-select-sm transfer-mode-select">
                    <option value="merge">合并导入</option>
                    <option value="replace">覆盖该组织看板</option>
                </select>
                <button class="btn btn-primary" id="${prefix}ImportOrgBtn" type="button" disabled>校验通过后导入</button>
            </div>
            <div class="transfer-report" id="${prefix}ImportOrgReport"></div>
        </div>
    `;
}

function renderBoardTransferSection(options = {}) {
    const {
        prefix = "ownerTransfer",
        boardDesc = "导出/导入您创建的单个看板（含画布/脑图/表格/描述数据）。",
    } = options;
    const boards = getOwnedBoards();
    const boardOptions = boards.length
        ? boards
              .map(
                  (board) =>
                      `<option value="${escapeHtml(board.id)}">${escapeHtml(formatBoardTransferOptionLabel(board))}</option>`
              )
              .join("")
        : `<option value="">暂无看板</option>`;

    return `
        <div class="transfer-section">
            <h3>看板导入导出</h3>
            <p class="transfer-desc">${boardDesc}</p>
            <div class="transfer-field-row">
                <label class="field-label" for="${prefix}ExportBoardSelect">选择看板</label>
                <select id="${prefix}ExportBoardSelect" class="form-select">${boardOptions}</select>
            </div>
            <div class="transfer-actions">
                <button class="btn btn-outline-primary" id="${prefix}ExportBoardBtn" type="button" ${boards.length ? "" : "disabled"}>导出看板 .dat</button>
                <label class="btn btn-outline-secondary transfer-file-btn">
                    选择看板包…
                    <input id="${prefix}ImportBoardFile" type="file" accept=".dat,application/json,text/plain" hidden>
                </label>
                <select id="${prefix}ImportBoardMode" class="form-select form-select-sm transfer-mode-select">
                    <option value="merge">合并导入（自动分配新 ID）</option>
                    <option value="replace">同 ID 覆盖</option>
                </select>
                <button class="btn btn-primary" id="${prefix}ImportBoardBtn" type="button" disabled>校验通过后导入</button>
            </div>
            <div class="transfer-report" id="${prefix}ImportBoardReport"></div>
        </div>
    `;
}

function renderOrgBoardTransferBlock(options = {}) {
    return renderOrgTransferSection(options) + renderBoardTransferSection(options);
}

function renderUserBoardTransferPanel() {
    return `
        <div class="settings-panel">
            <h2>看板导入导出</h2>
            <p class="panel-desc">
                导出/导入单个看板数据包（.dat），含列表、卡片及画布/脑图/表格/描述数据。
                数据包内会携带组织名称与唯一标识；导入时将自动创建或归并到已有组织，无需单独导出组织。
                分享的看板不在此列表中。
            </p>
            ${renderBoardTransferSection({
                prefix: "personalBoardTransfer",
                boardDesc: "选择看板导出；导入时根据包内组织信息自动归并到您的组织列表。",
            })}
        </div>
    `;
}

function renderBoardComparePanel() {
    return `
        <div class="compare-page-wrap">
        <div class="settings-panel">
            <h2>多平台看板对比</h2>
            <p class="panel-desc">
                将<strong>当前实例</strong>与另一台 BoardFlow 部署进行渐进式对比。数据按「账号 → 看板」分批拉取，不会一次性导出全量。
                远程实例需开启 <code>FEDERATION_COMPARE_ENABLED=1</code> 并配置相同令牌。
            </p>

            <div class="compare-config">
                <label class="compare-field">
                    <span>远程地址</span>
                    <input id="compareRemoteUrlInput" type="url" placeholder="https://board-flow-wheat.vercel.app" autocomplete="off">
                </label>
                <label class="compare-field">
                    <span>联邦令牌</span>
                    <input id="compareRemoteTokenInput" type="password" placeholder="与远程 FEDERATION_COMPARE_TOKEN 一致" autocomplete="off">
                </label>
                <label class="compare-field">
                    <span>看板配对方式</span>
                    <select id="compareMatchModeSelect">
                        <option value="by_title">按标题 + 组织自动配对</option>
                        <option value="by_id">按看板 ID 配对</option>
                        <option value="manual">手动指定（后续阶段）</option>
                    </select>
                </label>
                <div class="compare-field compare-options">
                    <span>对比深度</span>
                    <label class="compare-option"><input id="compareListsOption" type="checkbox" checked> 列表结构</label>
                    <label class="compare-option"><input id="compareCardsOption" type="checkbox" checked> 卡片摘要</label>
                    <label class="compare-option"><input id="compareDescriptionOption" type="checkbox"> 卡片描述（较慢）</label>
                </div>
            </div>

            <div class="transfer-actions compare-actions">
                <button class="btn btn-outline-primary" id="compareProbeBtn" type="button">探测远程连接</button>
                <button class="btn btn-primary" id="compareRunBtn" type="button" disabled>开始对比</button>
                <button class="btn btn-outline-secondary" id="compareResumeBtn" type="button" hidden>继续对比</button>
            </div>

            <div class="compare-remote-health" id="compareRemoteHealth" hidden></div>

            <div class="transfer-clear-progress compare-progress" id="compareProgress" hidden>
                <div class="transfer-clear-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100">
                    <div class="transfer-clear-progress-fill" id="compareProgressFill"></div>
                </div>
                <p class="transfer-clear-progress-text" id="compareProgressText"></p>
            </div>

            <div class="compare-workspace" id="compareWorkspace" hidden>
                <div class="compare-sync-feedback" id="compareSyncFeedback" hidden role="status" aria-live="polite"></div>
                <div class="compare-workspace-toolbar">
                    <div class="compare-filter-group" role="tablist" aria-label="对比结果筛选">
                        <button class="compare-filter-btn active" type="button" data-compare-filter="all">全部</button>
                        <button class="compare-filter-btn" type="button" data-compare-filter="changed">有差异</button>
                        <button class="compare-filter-btn" type="button" data-compare-filter="equal">一致</button>
                        <button class="compare-filter-btn" type="button" data-compare-filter="only_local">仅本地</button>
                        <button class="compare-filter-btn" type="button" data-compare-filter="only_remote">仅远程</button>
                    </div>
                    <div class="compare-collapse-toolbar">
                        <button class="btn btn-sm btn-outline-secondary" type="button" id="compareExpandAllBtn">全部展开</button>
                        <button class="btn btn-sm btn-outline-secondary" type="button" id="compareCollapseAllBtn">全部折叠</button>
                    </div>
                    <p class="compare-workspace-hint">左右对照：一侧有、一侧无时只显示存在的一侧（类似 Beyond Compare / Navicat）</p>
                </div>

                <div class="compare-diff-shell">
                    <div class="compare-diff-header">
                        <div class="compare-diff-col compare-diff-col--local">本地</div>
                        <div class="compare-diff-col compare-diff-col--status">状态</div>
                        <div class="compare-diff-col compare-diff-col--remote">远程</div>
                    </div>
                    <div class="compare-diff-body" id="compareDiffBody"></div>
                </div>
            </div>

            <div class="compare-summary" id="compareSummary" hidden></div>
        </div>
        <div class="compare-detail-drawer" id="compareDetailDrawer" hidden>
            <div class="compare-detail-backdrop" id="compareDetailBackdrop"></div>
            <div class="compare-detail-panel compare-detail-panel--wide" role="dialog" aria-modal="true" aria-labelledby="compareDetailTitle">
                <div class="compare-detail-head">
                    <h3 id="compareDetailTitle">对比详情</h3>
                    <button class="btn btn-sm btn-outline-secondary" id="compareDetailCloseBtn" type="button">关闭</button>
                </div>
                <div class="compare-detail-body" id="compareDetailBody"></div>
            </div>
        </div>
        </div>
    `;
}

const compareUiState = {
    sessionId: null,
    remoteHealth: null,
    accounts: new Map(),
    accountPairs: [],
    boardPairs: [],
    boardResults: [],
    activeFilter: "all",
    expandedPairIndex: null,
    canResume: false,
    resumeFromPairIndex: 0,
    collapsedKeys: new Set(),
    collapseInitialized: false,
};

const COMPARE_BOARD_STATUS_GROUPS = [
    { key: "changed", label: "有差异", statuses: new Set(["changed", "error"]) },
    { key: "only_local", label: "仅本地", statuses: new Set(["only_local"]) },
    { key: "only_remote", label: "仅远程", statuses: new Set(["only_remote"]) },
    { key: "equal", label: "一致", statuses: new Set(["equal"]) },
    { key: "pending", label: "对比中", statuses: new Set(["pending"]) },
];

function resetCompareUiState() {
    compareUiState.sessionId = null;
    compareUiState.remoteHealth = null;
    compareUiState.accounts = new Map();
    compareUiState.accountPairs = [];
    compareUiState.boardPairs = [];
    compareUiState.boardResults = [];
    compareUiState.activeFilter = "all";
    compareUiState.expandedPairIndex = null;
    compareUiState.canResume = false;
    compareUiState.resumeFromPairIndex = 0;
    compareUiState.collapsedKeys = new Set();
    compareUiState.collapseInitialized = false;
}

function isCompareCollapsed(key) {
    return compareUiState.collapsedKeys.has(key);
}

function toggleCompareCollapsed(key) {
    if (compareUiState.collapsedKeys.has(key)) {
        compareUiState.collapsedKeys.delete(key);
    } else {
        compareUiState.collapsedKeys.add(key);
    }
}

function setAllCompareCollapsed(collapsed) {
    if (collapsed) {
        for (const node of document.querySelectorAll("[data-collapse-key]")) {
            compareUiState.collapsedKeys.add(node.dataset.collapseKey);
        }
    } else {
        compareUiState.collapsedKeys.clear();
    }
    renderCompareWorkspace();
}

function ensureCompareCollapseDefaults() {
    if (compareUiState.collapseInitialized) {
        return;
    }
    const boardCount = compareUiState.boardPairs.length;
    const accountCount = compareUiState.accountPairs.length;
    if (!boardCount && !accountCount) {
        return;
    }
    compareUiState.collapseInitialized = true;
    compareUiState.collapsedKeys = new Set();

    if (boardCount > 8 && accountCount > 0) {
        compareUiState.collapsedKeys.add("section:accounts");
    }
    if (boardCount > 5) {
        compareUiState.collapsedKeys.add("status:equal");
    }
    if (boardCount > 20) {
        compareUiState.collapsedKeys.add("status:pending");
    }
}

function getComparePairRowStatus(pair, pairIndex) {
    const result = getCompareResultForPair(pairIndex);
    const pairStatus = pair.status || "matched";
    const status = result?.status || (pairStatus === "matched" ? "pending" : pairStatus);
    if (status === "pending" && pairStatus !== "matched") {
        return pairStatus;
    }
    return status;
}

function collectVisibleCompareBoardGroups() {
    const buckets = new Map(
        COMPARE_BOARD_STATUS_GROUPS.map((group) => [
            group.key,
            { ...group, accounts: new Map(), total: 0 },
        ]),
    );

    for (let index = 0; index < compareUiState.boardPairs.length; index += 1) {
        const pair = compareUiState.boardPairs[index];
        const pairStatus = pair.status || "matched";
        const rowStatus = getComparePairRowStatus(pair, index);
        const filterStatus = rowStatus === "pending" ? pairStatus : rowStatus;
        if (!compareRowMatchesFilter(filterStatus, pairStatus)) {
            continue;
        }
        const statusGroup = COMPARE_BOARD_STATUS_GROUPS.find((group) => group.statuses.has(rowStatus));
        const bucket = buckets.get(statusGroup?.key || "changed");
        const accountKey = `${pair.tenant_type || ""}:${pair.tenant_id || ""}`;
        const accountLabel = pair.display_name || accountKey || "未命名账号";
        if (!bucket.accounts.has(accountKey)) {
            bucket.accounts.set(accountKey, { key: accountKey, label: accountLabel, items: [] });
        }
        bucket.accounts.get(accountKey).items.push({ pair, index, rowStatus });
        bucket.total += 1;
    }

    return COMPARE_BOARD_STATUS_GROUPS.map((group) => buckets.get(group.key)).filter((group) => group.total > 0);
}

function renderCompareCollapseHeader(key, label, count, level = 0) {
    const collapsed = isCompareCollapsed(key);
    const levelClass =
        level === 2 ? "compare-collapse-header--account" : level === 1 ? "compare-collapse-header--status" : "compare-collapse-header--section";
    return `
        <button
            type="button"
            class="compare-collapse-header ${levelClass} ${collapsed ? "is-collapsed" : ""}"
            data-collapse-key="${escapeHtml(key)}"
            aria-expanded="${collapsed ? "false" : "true"}"
        >
            <span class="compare-collapse-chevron" aria-hidden="true">${collapsed ? "▶" : "▼"}</span>
            <span class="compare-collapse-title">${escapeHtml(label)}</span>
            ${count != null ? `<span class="compare-collapse-count">${count}</span>` : ""}
        </button>
    `;
}

function renderCompareCollapseBody(key, content) {
    const collapsed = isCompareCollapsed(key);
    if (!content) {
        return "";
    }
    return `<div class="compare-collapse-body ${collapsed ? "is-collapsed" : ""}" data-collapse-body="${escapeHtml(key)}">${content}</div>`;
}

function renderCompareBoardGroupContent(statusKey, statusGroup) {
    const accountGroups = [...statusGroup.accounts.values()];
    if (!accountGroups.length) {
        return "";
    }

    const useAccountGroups = accountGroups.length > 1 || compareUiState.boardPairs.length > 12;
    if (!useAccountGroups) {
        return accountGroups
            .flatMap((accountGroup) =>
                accountGroup.items.map(({ pair, index }) =>
                    renderCompareBoardPairRow(pair, index, getCompareResultForPair(index)),
                ),
            )
            .join("");
    }

    return accountGroups
        .map((accountGroup) => {
            const groupKey = `group:${statusKey}:${accountGroup.key}`;
            const rows = accountGroup.items
                .map(({ pair, index }) => renderCompareBoardPairRow(pair, index, getCompareResultForPair(index)))
                .join("");
            if (!rows) {
                return "";
            }
            return (
                renderCompareCollapseHeader(groupKey, accountGroup.label, accountGroup.items.length, 2) +
                renderCompareCollapseBody(groupKey, rows)
            );
        })
        .join("");
}

function updateCompareProgress(event) {
    const wrap = document.getElementById("compareProgress");
    const fill = document.getElementById("compareProgressFill");
    const text = document.getElementById("compareProgressText");
    if (!wrap || !fill || !text) {
        return;
    }
    wrap.hidden = false;
    const percent = Number.isFinite(event?.percent) ? event.percent : 0;
    fill.style.width = `${percent}%`;
    fill.parentElement?.setAttribute("aria-valuenow", String(percent));
    text.textContent = describeCompareEvent(event);
}

function describeCompareEvent(event) {
    const step = event?.step || "";
    if (step === "session_started") {
        return "对比会话已启动…";
    }
    if (step === "accounts_local") {
        return `正在拉取本地账号（本批 ${(event.items || []).length} 个）…`;
    }
    if (step === "accounts_remote") {
        return `正在拉取远程账号（本批 ${(event.items || []).length} 个）…`;
    }
    if (step === "accounts_matched") {
        const matched = (event.pairs || []).filter((item) => item.status === "matched").length;
        return `账号对齐完成：${matched} 组匹配`;
    }
    if (step === "boards_local") {
        return `本地看板 · ${event.display_name || event.tenant_id}（本批 ${(event.items || []).length} 个）`;
    }
    if (step === "boards_remote") {
        return `远程看板 · ${event.display_name || event.tenant_id}（本批 ${(event.items || []).length} 个）`;
    }
    if (step === "session_resumed") {
        return `从断点继续，从第 ${(event.resume_from_pair_index || 0) + 1} 组看板开始…`;
    }
    if (step === "board_pair_queued") {
        return `排队对比：${event.local_title || event.local_board_id || "—"} ↔ ${event.remote_title || event.remote_board_id || "—"}`;
    }
    if (step === "board_meta_diff") {
        return `元数据对比 · 看板 ${event.local_board_id || ""}`;
    }
    if (step === "board_lists_diff") {
        return `列表结构对比 · 看板 ${event.local_board_id || ""}`;
    }
    if (step === "board_cards_diff") {
        return `卡片对比 · 列表 ${event.list_id || ""}`;
    }
    if (step === "board_pair_done") {
        const status = event.summary?.status || "equal";
        return `看板对比完成：${compareStatusLabel(status)}`;
    }
    if (step === "session_done") {
        const totals = event.totals || {};
        return `全部完成：一致 ${totals.boards_equal || 0} · 有差异 ${totals.boards_changed || 0}`;
    }
    if (step === "error") {
        return event.message || "对比失败";
    }
    return event?.message || "处理中…";
}

function ensureCompareAccountNode(accountKey, displayName, status) {
    if (!compareUiState.accounts.has(accountKey)) {
        compareUiState.accounts.set(accountKey, {
            displayName,
            status,
            localBoards: [],
            remoteBoards: [],
        });
    }
    const node = compareUiState.accounts.get(accountKey);
    if (displayName) {
        node.displayName = displayName;
    }
    if (status) {
        node.status = status;
    }
    return node;
}

function accountKeyFromParts(tenantType, tenantId) {
    return `${tenantType}:${tenantId}`;
}

function compareBoardSideLabel(pair, side) {
    if (side === "local") {
        if (!pair.local_board_id && pair.status === "only_remote") {
            return null;
        }
        const title = pair.local_title || pair.local_board_id || "—";
        const org = normalizeBoardOrganization(pair.local_organization);
        return { title, org, id: pair.local_board_id || "" };
    }
    if (!pair.remote_board_id && pair.status === "only_local") {
        return null;
    }
    const title = pair.remote_title || pair.remote_board_id || "—";
    const org = normalizeBoardOrganization(pair.remote_organization);
    return { title, org, id: pair.remote_board_id || "" };
}

function renderCompareBoardCell(sideInfo, side) {
    if (!sideInfo) {
        return `<div class="compare-cell compare-cell--empty compare-cell--${side}"><span class="compare-cell-empty-mark">—</span></div>`;
    }
    return `
        <div class="compare-cell compare-cell--${side}">
            <div class="compare-cell-title">${escapeHtml(sideInfo.title)}</div>
            <div class="compare-cell-meta">${escapeHtml(sideInfo.org)}${sideInfo.id ? ` · ID ${escapeHtml(sideInfo.id)}` : ""}</div>
        </div>
    `;
}

function getCompareResultForPair(pairIndex) {
    return compareUiState.boardResults.find((item) => Number(item.pair_index) === Number(pairIndex)) || null;
}

function compareRowMatchesFilter(status, pairStatus) {
    const filter = compareUiState.activeFilter || "all";
    if (filter === "all") {
        return true;
    }
    if (filter === "changed") {
        return status === "changed" || status === "error";
    }
    if (filter === "equal") {
        return status === "equal";
    }
    if (filter === "only_local") {
        return pairStatus === "only_local" || status === "only_local";
    }
    if (filter === "only_remote") {
        return pairStatus === "only_remote" || status === "only_remote";
    }
    return true;
}

function renderCompareAccountPairRow(pair, accountPairIndex) {
    const status = pair.status || "matched";
    const localName = pair.local?.display_name || pair.local?.tenant_id || "—";
    const remoteName = pair.remote?.display_name || pair.remote?.tenant_id || "—";
    const localCell =
        status === "only_remote"
            ? `<div class="compare-cell compare-cell--empty compare-cell--local"><span class="compare-cell-empty-mark">—</span></div>`
            : `<div class="compare-cell compare-cell--local"><div class="compare-cell-title">${escapeHtml(localName)}</div><div class="compare-cell-meta">账号</div></div>`;
    const remoteCell =
        status === "only_local"
            ? `<div class="compare-cell compare-cell--empty compare-cell--remote"><span class="compare-cell-empty-mark">—</span></div>`
            : `<div class="compare-cell compare-cell--remote"><div class="compare-cell-title">${escapeHtml(remoteName)}</div><div class="compare-cell-meta">账号</div></div>`;
    return `
        <div class="compare-diff-row compare-diff-row--account compare-diff-row--${escapeHtml(status)}">
            ${localCell}
            <div class="compare-cell compare-cell--status">
                ${renderCompareAccountSyncActions(accountPairIndex, pair)}
                <span class="compare-result-badge compare-result-badge--${escapeHtml(status === "matched" ? "equal" : status)}">${escapeHtml(status === "matched" ? "账号匹配" : compareStatusLabel(status))}</span>
            </div>
            ${remoteCell}
        </div>
    `;
}

function renderCompareAccountSyncActions(accountPairIndex, pair) {
    if (!compareUiState.sessionId) {
        return "";
    }
    const status = pair.status || "matched";
    const canToRemote = status !== "only_remote" && Boolean(pair.local);
    const canToLocal = status !== "only_local" && Boolean(pair.remote);
    if (!canToRemote && !canToLocal) {
        return "";
    }
    return `
        <div class="compare-sync-actions">
            <button class="compare-sync-btn" type="button" title="该账号全部看板：远程 → 本地" data-sync-scope="account" data-sync-direction="to_local" data-account-pair-index="${accountPairIndex}" ${canToLocal ? "" : "disabled"} aria-label="账号全部看板同步到本地">←</button>
            <button class="compare-sync-btn" type="button" title="该账号全部看板：本地 → 远程" data-sync-scope="account" data-sync-direction="to_remote" data-account-pair-index="${accountPairIndex}" ${canToRemote ? "" : "disabled"} aria-label="账号全部看板同步到远程">→</button>
        </div>
    `;
}

function renderCompareSyncActions(pairIndex, pair, status) {
    if (status === "pending" || status === "error" || !compareUiState.sessionId) {
        return "";
    }
    const pairStatus = pair.status || "matched";
    const canToRemote = pairStatus !== "only_remote" && Boolean(pair.local_board_id);
    const canToLocal = pairStatus !== "only_local" && Boolean(pair.remote_board_id);
    if (!canToRemote && !canToLocal) {
        return "";
    }
    return `
        <div class="compare-sync-actions">
            <button class="compare-sync-btn" type="button" title="远程 → 本地（← 复制）" data-sync-scope="board" data-sync-direction="to_local" data-pair-index="${pairIndex}" ${canToLocal ? "" : "disabled"} aria-label="远程同步到本地">←</button>
            <button class="compare-sync-btn" type="button" title="本地 → 远程（→ 复制）" data-sync-scope="board" data-sync-direction="to_remote" data-pair-index="${pairIndex}" ${canToRemote ? "" : "disabled"} aria-label="本地同步到远程">→</button>
        </div>
    `;
}

function renderCompareBoardPairRow(pair, pairIndex, result) {
    const pairStatus = pair.status || "matched";
    const status = result?.status || (pairStatus === "matched" ? "pending" : pairStatus);
    if (!compareRowMatchesFilter(status === "pending" ? pairStatus : status, pairStatus)) {
        return "";
    }
    const localInfo = compareBoardSideLabel(pair, "local");
    const remoteInfo = compareBoardSideLabel(pair, "remote");
    const isExpanded = Number(compareUiState.expandedPairIndex) === Number(pairIndex);
    const statusKey = status === "pending" ? pairStatus : status;
    const badgeLabel = status === "pending" ? "对比中…" : compareStatusLabel(status);
    return `
        <div class="compare-diff-row compare-diff-row--board compare-diff-row--${escapeHtml(statusKey)} ${isExpanded ? "is-expanded" : ""}" data-pair-index="${pairIndex}">
            ${renderCompareBoardCell(localInfo, "local")}
            <div class="compare-cell compare-cell--status">
                ${renderCompareSyncActions(pairIndex, pair, status)}
                <span class="compare-result-badge compare-result-badge--${escapeHtml(statusKey === "pending" ? "changed" : statusKey)}">${escapeHtml(badgeLabel)}</span>
                <button class="btn btn-sm btn-link compare-row-detail-btn" type="button" data-pair-index="${pairIndex}" ${status === "pending" ? "disabled" : ""}>${isExpanded ? "收起" : "详情"}</button>
            </div>
            ${renderCompareBoardCell(remoteInfo, "remote")}
        </div>
        ${
            isExpanded
                ? `<div class="compare-diff-expand" data-pair-index="${pairIndex}"><div class="compare-diff-expand-inner" id="compareExpandBody-${pairIndex}">${renderCompareDetailContent(result) || '<p class="compare-detail-empty">加载中…</p>'}</div></div>`
                : ""
        }
    `;
}

function renderCompareWorkspace() {
    const workspace = document.getElementById("compareWorkspace");
    const body = document.getElementById("compareDiffBody");
    if (!workspace || !body) {
        return;
    }
    const hasRows = compareUiState.accountPairs.length || compareUiState.boardPairs.length;
    if (!hasRows) {
        workspace.hidden = true;
        body.innerHTML = "";
        return;
    }
    workspace.hidden = false;
    ensureCompareCollapseDefaults();

    const sections = [];
    if (compareUiState.accountPairs.length) {
        const accountRows = compareUiState.accountPairs
            .map((pair, index) => renderCompareAccountPairRow(pair, index))
            .join("");
        sections.push(renderCompareCollapseHeader("section:accounts", "账号对齐", compareUiState.accountPairs.length, 0));
        sections.push(renderCompareCollapseBody("section:accounts", accountRows));
    }

    const boardStatusGroups = collectVisibleCompareBoardGroups();
    if (boardStatusGroups.length) {
        const visibleBoardCount = boardStatusGroups.reduce((sum, group) => sum + group.total, 0);
        const boardsContent = boardStatusGroups
            .map((statusGroup) => {
                const statusKey = `status:${statusGroup.key}`;
                const inner = renderCompareBoardGroupContent(statusGroup.key, statusGroup);
                return renderCompareCollapseHeader(statusKey, statusGroup.label, statusGroup.total, 1) + renderCompareCollapseBody(statusKey, inner);
            })
            .join("");
        sections.push(renderCompareCollapseHeader("section:boards", "看板对比", visibleBoardCount, 0));
        sections.push(renderCompareCollapseBody("section:boards", boardsContent));
    }

    body.innerHTML = sections.filter(Boolean).join("") || '<p class="compare-detail-empty">当前筛选下无结果</p>';
    bindCompareWorkspaceRows();
}

function bindCompareWorkspaceRows() {
    document.querySelectorAll(".compare-collapse-header").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const key = button.dataset.collapseKey;
            if (!key) {
                return;
            }
            toggleCompareCollapsed(key);
            const collapsed = isCompareCollapsed(key);
            button.classList.toggle("is-collapsed", collapsed);
            button.setAttribute("aria-expanded", collapsed ? "false" : "true");
            const chevron = button.querySelector(".compare-collapse-chevron");
            if (chevron) {
                chevron.textContent = collapsed ? "▶" : "▼";
            }
            const bodyNode = document.querySelector(`[data-collapse-body="${CSS.escape(key)}"]`);
            if (bodyNode) {
                bodyNode.classList.toggle("is-collapsed", collapsed);
            }
        });
    });

    document.querySelectorAll(".compare-sync-btn").forEach((button) => {
        button.addEventListener("click", async (event) => {
            event.stopPropagation();
            if (button.disabled) {
                return;
            }
            const direction = button.dataset.syncDirection;
            const scope = button.dataset.syncScope || "board";
            if (scope === "account") {
                const accountPairIndex = Number(button.dataset.accountPairIndex);
                await syncCompareAccountPair(accountPairIndex, direction, button);
                return;
            }
            const pairIndex = Number(button.dataset.pairIndex);
            await syncComparePair(pairIndex, direction, button);
        });
    });

    document.querySelectorAll(".compare-row-detail-btn").forEach((button) => {
        button.addEventListener("click", async (event) => {
            event.stopPropagation();
            const pairIndex = Number(button.dataset.pairIndex);
            if (Number(compareUiState.expandedPairIndex) === pairIndex) {
                compareUiState.expandedPairIndex = null;
                renderCompareWorkspace();
                return;
            }
            compareUiState.expandedPairIndex = pairIndex;
            renderCompareWorkspace();
            const result = getCompareResultForPair(pairIndex);
            if (!result && compareUiState.sessionId) {
                try {
                    const loaded = await fetchComparePairDetail(pairIndex);
                    const existingIndex = compareUiState.boardResults.findIndex(
                        (item) => Number(item.pair_index) === pairIndex,
                    );
                    if (existingIndex >= 0) {
                        compareUiState.boardResults[existingIndex] = loaded;
                    } else {
                        compareUiState.boardResults.push(loaded);
                    }
                    renderCompareWorkspace();
                } catch (error) {
                    const expandBody = document.getElementById(`compareExpandBody-${pairIndex}`);
                    if (expandBody) {
                        expandBody.innerHTML = `<p class="compare-detail-error">${escapeHtml(error.message || "加载失败")}</p>`;
                    }
                }
            }
        });
    });
}

function bindCompareFilters() {
    document.querySelectorAll("[data-compare-filter]").forEach((button) => {
        button.addEventListener("click", () => {
            compareUiState.activeFilter = button.dataset.compareFilter || "all";
            document.querySelectorAll("[data-compare-filter]").forEach((node) => {
                node.classList.toggle("active", node === button);
            });
            renderCompareWorkspace();
        });
    });

    document.getElementById("compareExpandAllBtn")?.addEventListener("click", () => {
        setAllCompareCollapsed(false);
    });
    document.getElementById("compareCollapseAllBtn")?.addEventListener("click", () => {
        setAllCompareCollapsed(true);
    });
}

function compareStatusLabel(status) {
    const labels = {
        equal: "一致",
        changed: "有差异",
        only_local: "仅本地",
        only_remote: "仅远程",
        error: "错误",
        pending: "对比中",
    };
    return labels[status] || status || "—";
}

function formatCompareRequestError(response, rawText) {
    const text = (rawText || "").trim();
    if (response.status === 404) {
        if (/requested URL was not found/i.test(text)) {
            return "同步接口不存在（404）。请确认服务已更新到 v0.2.9 并已重启；若刚重启过，请重新「探测远程连接」并「开始对比」后再同步。";
        }
    }
    if (!text) {
        return `请求失败（HTTP ${response.status}）`;
    }
    try {
        const payload = JSON.parse(text);
        if (payload && typeof payload.message === "string" && payload.message.trim()) {
            if (/requested URL was not found/i.test(payload.message)) {
                return "同步接口不存在（404）。请确认服务已更新到 v0.2.9 并已重启；若刚重启过，请重新「探测远程连接」并「开始对比」后再同步。";
            }
            return payload.message;
        }
    } catch (error) {
        // fall through
    }
    return text.slice(0, 240);
}

function parseCompareJsonResponse(response) {
    return response.text().then((text) => {
        if (!text) {
            return {};
        }
        try {
            return JSON.parse(text);
        } catch (error) {
            throw new Error(formatCompareRequestError(response, text));
        }
    });
}

function showCompareSyncFeedback(message, type = "info") {
    const box = document.getElementById("compareSyncFeedback");
    if (box) {
        box.hidden = false;
        box.className = `compare-sync-feedback compare-sync-feedback--${type}`;
        box.textContent = message;
        box.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
    if (type === "success") {
        showSuccess(message);
    } else if (type === "error") {
        showError(message);
        errorBox?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
}

function clearCompareSyncFeedback() {
    const box = document.getElementById("compareSyncFeedback");
    if (box) {
        box.hidden = true;
        box.textContent = "";
        box.className = "compare-sync-feedback";
    }
}

function isAppVersionAtLeast(version, target) {
    const left = String(version || "0").split(".").map((part) => Number.parseInt(part, 10) || 0);
    const right = String(target || "0").split(".").map((part) => Number.parseInt(part, 10) || 0);
    for (let index = 0; index < 3; index += 1) {
        const lv = left[index] || 0;
        const rv = right[index] || 0;
        if (lv > rv) {
            return true;
        }
        if (lv < rv) {
            return false;
        }
    }
    return true;
}

function renderCompareTree() {
    renderCompareWorkspace();
}

function renderCompareResults() {
    renderCompareWorkspace();
}

function renderCompareDetailContent(result) {
    if (!result) {
        return "<p>暂无详情</p>";
    }
    const sections = [];
    if (result.error) {
        sections.push(`<p class="compare-detail-error">${escapeHtml(result.error)}</p>`);
    }
    if (result.meta) {
        const fields = result.meta.fields || {};
        const fieldRows = Object.entries(fields)
            .map(([key, value]) => {
                const localValue = value?.local ?? "—";
                const remoteValue = value?.remote ?? "—";
                return `<tr><td>${escapeHtml(key)}</td><td>${escapeHtml(String(localValue))}</td><td>${escapeHtml(String(remoteValue))}</td></tr>`;
            })
            .join("");
        sections.push(`
            <section class="compare-detail-section">
                <h4>看板元数据 <span class="compare-result-badge compare-result-badge--${escapeHtml(result.meta.status || "equal")}">${escapeHtml(compareStatusLabel(result.meta.status))}</span></h4>
                ${fieldRows ? `<table class="compare-detail-table"><thead><tr><th>字段</th><th>本地</th><th>远程</th></tr></thead><tbody>${fieldRows}</tbody></table>` : '<p class="compare-detail-empty">无字段差异</p>'}
            </section>
        `);
    }
    if (result.lists) {
        const rows = [];
        for (const item of result.lists.removed || []) {
            rows.push(
                `<tr class="compare-side-row compare-side-row--only-local"><td>${escapeHtml(item.title || item.id)}</td><td class="compare-side-empty">—</td></tr>`,
            );
        }
        for (const item of result.lists.added || []) {
            rows.push(
                `<tr class="compare-side-row compare-side-row--only-remote"><td class="compare-side-empty">—</td><td>${escapeHtml(item.title || item.id)}</td></tr>`,
            );
        }
        for (const item of result.lists.changed || []) {
            const localTitle = item.fields?.title?.local ?? item.id;
            const remoteTitle = item.fields?.title?.remote ?? item.id;
            rows.push(
                `<tr class="compare-side-row compare-side-row--changed"><td>${escapeHtml(String(localTitle))}</td><td>${escapeHtml(String(remoteTitle))}</td></tr>`,
            );
        }
        sections.push(`
            <section class="compare-detail-section">
                <h4>列表结构 <span class="compare-result-badge compare-result-badge--${escapeHtml(result.lists.status || "equal")}">${escapeHtml(compareStatusLabel(result.lists.status))}</span></h4>
                ${
                    rows.length
                        ? `<table class="compare-side-table"><thead><tr><th>本地</th><th>远程</th></tr></thead><tbody>${rows.join("")}</tbody></table>`
                        : '<p class="compare-detail-empty">列表结构一致</p>'
                }
            </section>
        `);
    }
    const cardsByList = result.cards?.by_list || {};
    const listIds = Object.keys(cardsByList);
    if (listIds.length) {
        const cardsHtml = listIds
            .map((listId) => {
                const diff = cardsByList[listId] || {};
                const added = (diff.added || []).length;
                const removed = (diff.removed || []).length;
                const changed = (diff.changed || []).length;
                const status =
                    added || removed || changed
                        ? "changed"
                        : "equal";
                return `
                    <tr>
                        <td>列表 ${escapeHtml(listId)}</td>
                        <td>${removed ? `仅本地 ${removed}` : "—"}</td>
                        <td>${added ? `仅远程 ${added}` : "—"}</td>
                        <td>${changed ? `差异 ${changed}` : "—"}</td>
                    </tr>`;
            })
            .join("");
        sections.push(`
            <section class="compare-detail-section">
                <h4>卡片摘要</h4>
                <table class="compare-side-table">
                    <thead><tr><th>列表</th><th>本地</th><th>远程</th><th>变更</th></tr></thead>
                    <tbody>${cardsHtml}</tbody>
                </table>
            </section>
        `);
    }
    return sections.join("") || "<p>暂无详情</p>";
}

function updateCompareResumeButton() {
    const resumeBtn = document.getElementById("compareResumeBtn");
    if (!resumeBtn) {
        return;
    }
    resumeBtn.hidden = !compareUiState.canResume || !compareUiState.sessionId;
}

async function fetchComparePairDetail(pairIndex) {
    const response = await fetch(
        `/api/compare/sessions/${encodeURIComponent(compareUiState.sessionId)}/results?pair_index=${encodeURIComponent(pairIndex)}`,
    );
    const payload = await response.json();
    if (!response.ok) {
        throw new Error(payload.message || "加载对比详情失败");
    }
    return payload;
}

async function syncComparePair(pairIndex, direction, triggerButton) {
    if (!compareUiState.sessionId) {
        showCompareSyncFeedback("对比会话已失效，请先「探测远程连接」并重新「开始对比」。", "error");
        return;
    }
    const pair = compareUiState.boardPairs[pairIndex];
    if (!pair) {
        showCompareSyncFeedback("看板对不存在，请重新运行对比。", "error");
        return;
    }
    const directionLabel = direction === "to_remote" ? "本地 → 远程" : "远程 → 本地";
    const sideLabel = direction === "to_remote" ? pair.local_title || pair.local_board_id : pair.remote_title || pair.remote_board_id;
    const confirmed = window.confirm(`确定将「${sideLabel || "看板"}」${directionLabel} 同步？\n匹配看板将覆盖目标侧内容。`);
    if (!confirmed) {
        return;
    }

    clearCompareSyncFeedback();
    showCompareSyncFeedback(`正在同步「${sideLabel || "看板"}」…`, "info");

    const buttons = document.querySelectorAll(
        `.compare-sync-btn[data-sync-scope="board"][data-pair-index="${pairIndex}"]`,
    );
    buttons.forEach((node) => {
        node.disabled = true;
    });
    if (triggerButton) {
        triggerButton.textContent = "…";
    }

    try {
        const response = await fetch(`/api/compare/sessions/${encodeURIComponent(compareUiState.sessionId)}/sync`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            credentials: "same-origin",
            body: JSON.stringify({
                pair_index: pairIndex,
                direction,
                mode: "replace",
            }),
        });
        const payload = await parseCompareJsonResponse(response);
        if (!response.ok) {
            const message = payload.message || formatCompareRequestError(response, JSON.stringify(payload));
            if (message.includes("会话不存在") || message.includes("已过期")) {
                compareUiState.sessionId = null;
                throw new Error(`${message}。请先「探测远程连接」并重新「开始对比」。`);
            }
            throw new Error(message);
        }
        if (payload.queued) {
            compareUiState.boardPairs[pairIndex] = {
                ...compareUiState.boardPairs[pairIndex],
                ...payload.queued,
            };
        }
        if (payload.result) {
            const existingIndex = compareUiState.boardResults.findIndex(
                (item) => Number(item.pair_index) === pairIndex,
            );
            if (existingIndex >= 0) {
                compareUiState.boardResults[existingIndex] = payload.result;
            } else {
                compareUiState.boardResults.push(payload.result);
            }
        }
        compareUiState.expandedPairIndex = pairIndex;
        renderCompareWorkspace();
        showCompareSyncFeedback(payload.message || "同步成功", "success");
    } catch (error) {
        showCompareSyncFeedback(error.message || "同步失败", "error");
        renderCompareWorkspace();
    }
}

async function syncCompareAccountPair(accountPairIndex, direction, triggerButton) {
    if (!compareUiState.sessionId) {
        showCompareSyncFeedback("对比会话已失效，请先「探测远程连接」并重新「开始对比」。", "error");
        return;
    }
    const pair = compareUiState.accountPairs[accountPairIndex];
    if (!pair) {
        showCompareSyncFeedback("账号对不存在，请重新运行对比。", "error");
        return;
    }
    const accountName =
        pair.local?.display_name ||
        pair.remote?.display_name ||
        pair.local?.tenant_id ||
        pair.remote?.tenant_id ||
        "账号";
    const directionLabel = direction === "to_remote" ? "本地 → 远程" : "远程 → 本地";
    const confirmed = window.confirm(
        `确定将账号「${accountName}」下的全部看板 ${directionLabel} 同步？\n已匹配的看板将覆盖目标侧内容。`,
    );
    if (!confirmed) {
        return;
    }

    clearCompareSyncFeedback();
    showCompareSyncFeedback(`正在同步账号「${accountName}」下的看板…`, "info");

    const buttons = document.querySelectorAll(
        `.compare-sync-btn[data-sync-scope="account"][data-account-pair-index="${accountPairIndex}"]`,
    );
    buttons.forEach((node) => {
        node.disabled = true;
    });
    if (triggerButton) {
        triggerButton.textContent = "…";
    }

    try {
        const response = await fetch(
            `/api/compare/sessions/${encodeURIComponent(compareUiState.sessionId)}/sync-account`,
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                credentials: "same-origin",
                body: JSON.stringify({
                    account_pair_index: accountPairIndex,
                    direction,
                    mode: "replace",
                }),
            },
        );
        const payload = await parseCompareJsonResponse(response);
        if (!response.ok) {
            const message = payload.message || formatCompareRequestError(response, JSON.stringify(payload));
            if (message.includes("会话不存在") || message.includes("已过期")) {
                compareUiState.sessionId = null;
                throw new Error(`${message}。请先「探测远程连接」并重新「开始对比」。`);
            }
            throw new Error(message);
        }
        if (Array.isArray(payload.board_pairs)) {
            compareUiState.boardPairs = payload.board_pairs;
        }
        if (Array.isArray(payload.board_results)) {
            compareUiState.boardResults = payload.board_results;
        }
        renderCompareWorkspace();
        if (payload.error_count > 0) {
            showCompareSyncFeedback(payload.message || "部分看板同步失败", "error");
        } else {
            showCompareSyncFeedback(payload.message || "账号同步成功", "success");
        }
    } catch (error) {
        showCompareSyncFeedback(error.message || "账号同步失败", "error");
        renderCompareWorkspace();
    }
}

async function openCompareDetail(pairIndex) {
    const drawer = document.getElementById("compareDetailDrawer");
    const title = document.getElementById("compareDetailTitle");
    const body = document.getElementById("compareDetailBody");
    if (!drawer || !body || !compareUiState.sessionId) {
        return;
    }
    body.innerHTML = `<p class="compare-detail-empty">加载中…</p>`;
    drawer.hidden = false;
    try {
        const result = await fetchComparePairDetail(pairIndex);
        if (title) {
            title.textContent = `${result?.local_title || "本地"} ↔ ${result?.remote_title || "远程"}`;
        }
        body.innerHTML = renderCompareDetailContent(result);
    } catch (error) {
        body.innerHTML = `<p class="compare-detail-error">${escapeHtml(error.message || "加载失败")}</p>`;
    }
}

function closeCompareDetail() {
    const drawer = document.getElementById("compareDetailDrawer");
    if (drawer) {
        drawer.hidden = true;
    }
}

function renderCompareSummary(event) {
    const summary = document.getElementById("compareSummary");
    if (!summary) {
        return;
    }
    const totals = event?.totals || {};
    if (!event?.done) {
        summary.hidden = true;
        return;
    }
    summary.hidden = false;
    summary.innerHTML = `
        <p>本地账号 <strong>${totals.local_accounts || 0}</strong> · 远程账号 <strong>${totals.remote_accounts || 0}</strong> · 匹配账号 <strong>${totals.matched_accounts || 0}</strong></p>
        <p>看板对比：一致 <strong>${totals.boards_equal || 0}</strong> · 有差异 <strong>${totals.boards_changed || 0}</strong> · 仅本地 <strong>${totals.boards_only_local || 0}</strong> · 仅远程 <strong>${totals.boards_only_remote || 0}</strong></p>
    `;
    renderCompareResults();
}

function applyCompareStreamEvent(event) {
    if (!event) {
        return;
    }
    updateCompareProgress(event);

    if (event.step === "accounts_matched") {
        compareUiState.accountPairs = event.pairs || [];
        compareUiState.accounts.clear();
        for (const pair of compareUiState.accountPairs) {
            if (pair.local) {
                const key = accountKeyFromParts(pair.local.tenant_type, pair.local.tenant_id);
                ensureCompareAccountNode(key, pair.local.display_name, pair.status);
            }
            if (pair.remote && pair.status === "only_remote") {
                const key = accountKeyFromParts(pair.remote.tenant_type, pair.remote.tenant_id);
                ensureCompareAccountNode(key, pair.remote.display_name, pair.status);
            }
        }
        renderCompareWorkspace();
    }

    if (event.step === "boards_local" || event.step === "boards_remote") {
        const key = accountKeyFromParts(event.tenant_type, event.tenant_id);
        const node = ensureCompareAccountNode(key, event.display_name, "matched");
        const side = event.step === "boards_local" ? "local" : "remote";
        const target = side === "local" ? node.localBoards : node.remoteBoards;
        for (const board of event.items || []) {
            target.push({ ...board, side });
        }
        renderCompareWorkspace();
    }

    if (event.step === "board_pair_queued") {
        const pairIndex = Number(event.pair_index);
        compareUiState.boardPairs[pairIndex] = event;
        renderCompareWorkspace();
    }

    if (event.step === "board_pair_done" && event.summary) {
        const existingIndex = compareUiState.boardResults.findIndex(
            (item) => Number(item.pair_index) === Number(event.summary.pair_index),
        );
        if (existingIndex >= 0) {
            compareUiState.boardResults[existingIndex] = event.summary;
        } else {
            compareUiState.boardResults.push(event.summary);
        }
        renderCompareWorkspace();
    }

    if (event.step === "session_done") {
        compareUiState.collapseInitialized = false;
        renderCompareSummary(event);
    }
}

async function createCompareSession(payload) {
    const response = await fetch("/api/compare/sessions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
    });
    const result = await response.json();
    if (!response.ok) {
        throw new Error(result.message || "创建对比会话失败");
    }
    return result;
}

async function runCompareSession(sessionId, onProgress, runOptions = {}) {
    const response = await fetch(`/api/compare/sessions/${encodeURIComponent(sessionId)}/run`, {
        method: "POST",
        headers: {
            Accept: "application/x-ndjson",
            "Content-Type": "application/json",
        },
        body: JSON.stringify(runOptions || {}),
    });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.message || "对比请求失败");
    }
    if (!response.body) {
        throw new Error("浏览器不支持流式进度响应");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let lastEvent = null;

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                continue;
            }
            const event = JSON.parse(trimmed);
            lastEvent = event;
            onProgress?.(event);
            applyCompareStreamEvent(event);
            if (event.error && event.fatal) {
                throw new Error(event.message || "对比失败");
            }
        }
    }

    const tail = buffer.trim();
    if (tail) {
        const event = JSON.parse(tail);
        lastEvent = event;
        onProgress?.(event);
        applyCompareStreamEvent(event);
        if (event.error && event.fatal) {
            throw new Error(event.message || "对比失败");
        }
    }

    if (!lastEvent?.done) {
        compareUiState.canResume = Boolean(compareUiState.sessionId);
        compareUiState.resumeFromPairIndex = compareUiState.boardResults.length;
        updateCompareResumeButton();
        throw new Error("对比未完成，可点击「继续对比」从断点续跑");
    }
    compareUiState.canResume = false;
    updateCompareResumeButton();
    return lastEvent;
}

function bindBoardComparePanel() {
    const remoteUrlInput = document.getElementById("compareRemoteUrlInput");
    const remoteTokenInput = document.getElementById("compareRemoteTokenInput");
    const matchModeSelect = document.getElementById("compareMatchModeSelect");
    const probeBtn = document.getElementById("compareProbeBtn");
    const runBtn = document.getElementById("compareRunBtn");
    const resumeBtn = document.getElementById("compareResumeBtn");
    const healthBox = document.getElementById("compareRemoteHealth");

    if (!remoteUrlInput || !probeBtn || !runBtn) {
        return;
    }

    const runCompareFlow = async (runOptions = {}) => {
        const sessionId = compareUiState.sessionId;
        if (!sessionId) {
            showError("请先探测远程连接");
            return;
        }
        clearError();
        if (!runOptions.from_phase) {
            resetCompareUiState();
            compareUiState.sessionId = sessionId;
            renderCompareTree();
            const summaryEl = document.getElementById("compareSummary");
            if (summaryEl) {
                summaryEl.hidden = true;
            }
        }
        runBtn.disabled = true;
        resumeBtn.disabled = true;
        probeBtn.disabled = true;
        try {
            await runCompareSession(sessionId, updateCompareProgress, runOptions);
            showSuccess("多平台看板对比已完成");
        } catch (error) {
            showError(error.message || "对比失败");
        } finally {
            runBtn.disabled = false;
            resumeBtn.disabled = false;
            probeBtn.disabled = false;
            updateCompareResumeButton();
        }
    };

    const getPayload = () => ({
        remote_base_url: remoteUrlInput.value.trim(),
        remote_token: remoteTokenInput?.value || "",
        match_mode: matchModeSelect?.value || "by_title",
        pairs: [],
        options: {
            compare_lists: document.getElementById("compareListsOption")?.checked !== false,
            compare_cards: document.getElementById("compareCardsOption")?.checked !== false,
            compare_card_description: document.getElementById("compareDescriptionOption")?.checked === true,
        },
    });

    probeBtn.addEventListener("click", async () => {
        clearError();
        resetCompareUiState();
        renderCompareTree();
        const summaryEl = document.getElementById("compareSummary");
        const progressEl = document.getElementById("compareProgress");
        if (summaryEl) {
            summaryEl.hidden = true;
        }
        if (progressEl) {
            progressEl.hidden = true;
        }
        runBtn.disabled = true;
        probeBtn.disabled = true;
        try {
            const result = await createCompareSession(getPayload());
            compareUiState.sessionId = result.session_id;
            compareUiState.remoteHealth = result.remote_health;
            runBtn.disabled = false;
            if (healthBox) {
                healthBox.hidden = false;
                const health = result.remote_health || {};
                const federation = health.federation || {};
                const syncEnabled =
                    federation.sync_enabled === true || isAppVersionAtLeast(health.version, "0.2.6");
                const syncHint = syncEnabled
                    ? "支持看板同步写入"
                    : '<span class="compare-health-warn">远程版本较旧或未启用同步写入（需 v0.2.6+）</span>';
                healthBox.innerHTML = `
                    <p class="compare-health-ok">远程连接成功：${escapeHtml(health.label || health.version || "")} · 联邦 API v${escapeHtml(String(federation.api_version || ""))} · ${syncHint}</p>
                `;
            }
            showSuccess("远程连接探测成功");
        } catch (error) {
            if (healthBox) {
                healthBox.hidden = false;
                healthBox.innerHTML = `<p class="compare-health-error">${escapeHtml(error.message || "连接失败")}</p>`;
            }
            showError(error.message || "远程连接探测失败");
        } finally {
            probeBtn.disabled = false;
        }
    });

    runBtn.addEventListener("click", async () => {
        await runCompareFlow();
    });

    resumeBtn?.addEventListener("click", async () => {
        await runCompareFlow({
            from_phase: "diff",
            resume_from_pair_index: compareUiState.resumeFromPairIndex,
        });
    });

    document.getElementById("compareDetailCloseBtn")?.addEventListener("click", closeCompareDetail);
    document.getElementById("compareDetailBackdrop")?.addEventListener("click", closeCompareDetail);
    bindCompareFilters();
}

function renderDataTransferPanel() {
    return `
        <div class="settings-panel">
            <h2>数据导入导出</h2>
            <p class="panel-desc">
                支持 .dat 数据包：<strong>系统全量</strong>、<strong>单看板</strong>。
                看板包内携带组织名称与唯一标识，导入时自动创建或归并到已有组织。
                文件为 UTF-8 JSON，首行魔数 <code>BFLOW1</code>，含 SHA256 校验和（v2）。导入前会先执行完整性检查。
            </p>

            <div class="transfer-section">
                <h3>系统全量</h3>
                <p class="transfer-desc">
                    导出<strong>全部租户数据</strong>：超管看板、所有用户账号与各自看板、分享记录、分享索引，以及
                    <strong>系统设置</strong>（看板状态、卡片类型、组织列表、字体设置）。
                    导入将<strong>完全覆盖</strong>当前 Redis 中的 BoardFlow 数据（含上述全部内容）。
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

            ${renderBoardTransferSection({
                prefix: "adminTransfer",
                boardDesc:
                    "导出看板数据包（含组织标识与列表/卡片/编辑器数据）；导入时按包内组织信息自动创建或归并到已有组织。",
            })}

            <details class="transfer-danger-zone transfer-danger-details">
                <summary class="transfer-danger-summary">高级选项：清理全部系统数据</summary>
                <div class="transfer-danger-body">
                    <p class="transfer-desc">
                        清理将删除<strong>全部</strong>用户账号、看板、列表、卡片、分享记录与系统设置，恢复为初始空数据。
                        环境变量中的超管账号仍可登录；此操作不可撤销，建议先导出系统全量备份。
                    </p>
                    <div class="transfer-actions">
                        <button class="btn btn-sm btn-outline-danger" id="clearSystemDataBtn" type="button">清理所有系统数据</button>
                    </div>
                    <div class="transfer-clear-progress" id="clearSystemProgress" hidden>
                        <div class="transfer-clear-progress-bar" role="progressbar" aria-valuemin="0" aria-valuemax="100">
                            <div class="transfer-clear-progress-fill" id="clearSystemProgressFill"></div>
                        </div>
                        <p class="transfer-clear-progress-text" id="clearSystemProgressText"></p>
                    </div>
                </div>
            </details>
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
        users: "用户",
        shares: "分享记录",
        tenants: "涉及租户",
        board_owners: "看板归属",
        card_types: "卡片类型",
        board_statuses: "看板状态",
        board_title: "看板标题",
        organization: "组织名称",
        legacy: "旧版包",
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

async function validateTransferFile(file, { expectedKind, ownerOnly = false } = {}) {
    const formData = new FormData();
    formData.append("file", file);
    if (expectedKind) {
        formData.append("expected_kind", expectedKind);
    }
    if (ownerOnly) {
        formData.append("owner_only", "1");
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

async function importTransferFile(file, { expectedKind, mode, ownerOnly = false } = {}) {
    const formData = new FormData();
    formData.append("file", file);
    formData.append("mode", mode);
    if (expectedKind) {
        formData.append("expected_kind", expectedKind);
    }
    if (ownerOnly) {
        formData.append("owner_only", "1");
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

function updateClearSystemProgress(event) {
    const wrap = document.getElementById("clearSystemProgress");
    const fill = document.getElementById("clearSystemProgressFill");
    const text = document.getElementById("clearSystemProgressText");
    if (!wrap || !fill || !text) {
        return;
    }
    wrap.hidden = false;
    const percent = Number.isFinite(event?.percent) ? event.percent : 0;
    fill.style.width = `${percent}%`;
    fill.parentElement?.setAttribute("aria-valuenow", String(percent));
    text.textContent = event?.message || "";
}

async function clearAllSystemData(onProgress) {
    const response = await fetch("/api/data-transfer/clear-system", { method: "POST" });
    if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.message || "清理请求失败");
    }
    if (!response.body) {
        throw new Error("浏览器不支持流式进度响应");
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let lastEvent = null;

    while (true) {
        const { done, value } = await reader.read();
        if (done) {
            break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";
        for (const line of lines) {
            const trimmed = line.trim();
            if (!trimmed) {
                continue;
            }
            const event = JSON.parse(trimmed);
            lastEvent = event;
            onProgress?.(event);
            if (event.error) {
                throw new Error(event.message || "清理失败");
            }
        }
    }

    const tail = buffer.trim();
    if (tail) {
        const event = JSON.parse(tail);
        lastEvent = event;
        onProgress?.(event);
        if (event.error) {
            throw new Error(event.message || "清理失败");
        }
    }

    if (!lastEvent?.done) {
        throw new Error("清理未完成，请稍后重试");
    }
    return lastEvent;
}

function bindOrgBoardTransferBlock(options = {}) {
    const { prefix = "ownerTransfer", ownerOnly = true, kinds = ["organization", "board"] } = options;
    const transferState = {
        organization: { file: null, validation: null },
        board: { file: null, validation: null },
    };

    if (kinds.includes("organization")) {
        document.getElementById(`${prefix}ExportOrgBtn`)?.addEventListener("click", () => {
            const orgId = document.getElementById(`${prefix}ExportOrgSelect`)?.value;
            if (!orgId) {
                showError("请选择组织");
                return;
            }
            const scopeQuery = ownerOnly ? "?scope=owner" : "";
            downloadDat(
                `/api/data-transfer/export/organization/${encodeURIComponent(orgId)}${scopeQuery}`,
                "boardflow-org.dat"
            )
                .then(() => showSuccess("组织数据包已开始下载"))
                .catch((error) => showError(error.message || "导出失败"));
        });
    }

    if (kinds.includes("board")) {
        document.getElementById(`${prefix}ExportBoardBtn`)?.addEventListener("click", () => {
            const boardId = document.getElementById(`${prefix}ExportBoardSelect`)?.value;
            if (!boardId) {
                showError("请选择看板");
                return;
            }
            downloadDat(`/api/data-transfer/export/board/${encodeURIComponent(boardId)}`, "boardflow-board.dat")
                .then(() => showSuccess("看板数据包已开始下载"))
                .catch((error) => showError(error.message || "导出失败"));
        });
    }

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
            if (!file) {
                renderTransferReport(reportEl, null);
                return;
            }
            try {
                const validation = await validateTransferFile(file, {
                    expectedKind: kind,
                    ownerOnly: kind === "organization" && ownerOnly,
                });
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
            const mode = modeSelect?.value || "merge";
            try {
                await importTransferFile(file, {
                    expectedKind: kind,
                    mode,
                    ownerOnly: kind === "organization" && ownerOnly,
                });
                showSuccess("数据导入成功");
                await loadSettings();
                await loadBoards();
                renderSettingsPage(resolveSettingsTab());
            } catch (error) {
                showError(error.message || "导入失败");
            }
        });
    }

    if (kinds.includes("organization")) {
        wireImport("organization", `${prefix}ImportOrgFile`, `${prefix}ImportOrgReport`, `${prefix}ImportOrgBtn`, `${prefix}ImportOrgMode`);
    }
    if (kinds.includes("board")) {
        wireImport("board", `${prefix}ImportBoardFile`, `${prefix}ImportBoardReport`, `${prefix}ImportBoardBtn`, `${prefix}ImportBoardMode`);
    }
}

function bindDataTransferPanel() {
    const transferState = {
        system: { file: null, validation: null },
    };

    document.getElementById("exportSystemBtn")?.addEventListener("click", () => {
        downloadDat("/api/data-transfer/export/system", "boardflow-system.dat")
            .then(() => showSuccess("系统数据包已开始下载"))
            .catch((error) => showError(error.message || "导出失败"));
    });

    const fileInput = document.getElementById("importSystemFile");
    const reportEl = document.getElementById("importSystemReport");
    const importBtn = document.getElementById("importSystemBtn");

    fileInput?.addEventListener("change", async () => {
        const file = fileInput.files?.[0];
        transferState.system.file = file || null;
        transferState.system.validation = null;
        if (importBtn) {
            importBtn.disabled = true;
        }
        renderTransferReport(reportEl, null);
        if (!file) {
            return;
        }
        try {
            const validation = await validateTransferFile(file, { expectedKind: "system" });
            transferState.system.validation = validation;
            renderTransferReport(reportEl, validation);
            if (importBtn) {
                importBtn.disabled = !validation.valid;
            }
        } catch (error) {
            renderTransferReport(reportEl, {
                valid: false,
                kind: "system",
                errors: [error.message || "校验失败"],
                warnings: [],
                summary: {},
            });
        }
    });

    importBtn?.addEventListener("click", async () => {
        const file = transferState.system.file;
        const validation = transferState.system.validation;
        if (!file || !validation?.valid) {
            showError("请先选择并通过校验的数据包");
            return;
        }
        if (!window.confirm("确定用该系统包完全覆盖当前所有数据吗？此操作不可撤销。")) {
            return;
        }
        importBtn.disabled = true;
        try {
            await importTransferFile(file, { expectedKind: "system", mode: "replace" });
            await loadSettings();
            await loadBoards();
            showSuccess("数据导入成功");
            renderRoute();
        } catch (error) {
            showError(error.message || "导入失败");
            importBtn.disabled = false;
        }
    });

    const clearBtn = document.getElementById("clearSystemDataBtn");
    clearBtn?.addEventListener("click", () => {
        openConfirmDeleteDialog({
            title: "清理所有系统数据",
            message:
                "将删除 <strong>全部</strong> 用户、看板、分享与系统设置，恢复为初始空数据。环境变量中的超管账号仍可登录。此操作不可撤销。",
            onSubmit: async () => {
                confirmDeleteModal.hide();
                clearBtn.disabled = true;
                updateClearSystemProgress({ message: "正在启动清理…", percent: 0 });
                try {
                    await clearAllSystemData(updateClearSystemProgress);
                    await loadSettings();
                    await loadBoards();
                    showSuccess("系统数据已清理完成");
                    renderRoute();
                } finally {
                    clearBtn.disabled = false;
                }
            },
        });
    });

    bindOrgBoardTransferBlock({ prefix: "adminTransfer", ownerOnly: false, kinds: ["board"] });
}

function renderOrganizationSettingsPanel(organizations, isPersonal = false) {
    return `
        <div class="settings-panel">
            <h2>所属组织</h2>
            <p class="panel-desc">${
                isPersonal
                    ? "此处维护您账号下的项目组织，数据独立存储在您的用户空间，仅对您可见。与管理员的全局组织互不影响；不同用户之间组织名称允许重复，但在您名下不可重复。保存后可在新建或编辑看板时选择。"
                    : "「个人看板」为内置默认选项。此处维护超级管理员的全局组织；不同账户之间组织名称允许重复。保存后可在新建或编辑看板时选择。"
            }</p>
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
                <button class="btn btn-primary" id="saveOrganizationSettingsBtn" type="button" data-personal-orgs="${
                    isPersonal ? "1" : "0"
                }">保存组织设置</button>
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
    if (activeTab === "users") {
        loadUsersForSettings()
            .then((users) => {
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
                    ${renderUsersSettingsPanel(users)}
                </div>
            </div>
        </section>
    `;
                bindUsersSettingsPanel();
            })
            .catch((error) => showError(error.message || "加载用户失败"));
        return;
    }
    const statuses = getBoardStatuses();
    const organizations = getOrganizations();
    const panelHtml =
        activeTab === "data-transfer"
            ? renderDataTransferPanel()
            : activeTab === "board-compare"
              ? renderBoardComparePanel()
              : activeTab === "user-board-transfer"
                  ? renderUserBoardTransferPanel()
              : activeTab === "organizations" || activeTab === "my-organizations"
              ? renderOrganizationSettingsPanel(organizations, activeTab === "my-organizations")
              : activeTab === "fonts"
                ? renderFontSettingsPanel()
                : activeTab === "collaboration"
                  ? renderCollaborationSettingsPanel()
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

    if (activeTab === "board-compare") {
        bindBoardComparePanel();
        return;
    }

    if (activeTab === "fonts") {
        bindFontSettingsPanel();
        return;
    }

    if (activeTab === "collaboration") {
        bindCollaborationSettingsPanel();
        return;
    }

    if (activeTab === "organizations" || activeTab === "my-organizations") {
        document.getElementById("addOrganizationRowBtn").addEventListener("click", addOrganizationSettingsRow);
        document.getElementById("saveOrganizationSettingsBtn").addEventListener("click", saveOrganizationSettings);
        bindOrganizationSettingsRows();
        return;
    }

    if (activeTab === "user-board-transfer") {
        bindOrgBoardTransferBlock({
            prefix: "personalBoardTransfer",
            ownerOnly: true,
            kinds: ["board"],
        });
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

    const isPersonal = document.getElementById("saveOrganizationSettingsBtn")?.dataset.personalOrgs === "1";
    const endpoint = isPersonal ? "/api/settings/my-organizations" : "/api/settings/organizations";

    try {
        const result = await api(endpoint, {
            method: "PUT",
            body: JSON.stringify({ organizations }),
        });
        state.settings = result.settings || state.settings;
        await loadBoards();
        renderSettingsPage(isPersonal ? "my-organizations" : "organizations");
        showSuccess(isPersonal ? "所属组织已保存" : "组织列表已保存");
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
    loadSettings()
        .then(() => renderBoardListContent())
        .catch((error) => showError(error.message || "加载设置失败"));
}

function renderBoardHubSidebar(hub = state.boardHub) {
    const organizations = getOrganizations();
    const sharedOrganizationGroups = getSharedOrganizationNavGroups();
    const mineExpanded = state.boardHubGroups.mine;
    const projectsExpanded = state.boardHubGroups.projects;
    const sharedProjectsExpanded = state.boardHubGroups.sharedProjects;

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
                                : `<span class="board-hub-nav-empty">暂无项目，可在设置中维护</span>`
                        }
                    </div>
                </div>

                ${
                    sharedOrganizationGroups.length
                        ? `<div class="board-hub-nav-group ${sharedProjectsExpanded ? "expanded" : ""}">
                    <button class="board-hub-nav-group-head" data-toggle-hub-group="sharedProjects" type="button">
                        <span class="board-hub-nav-group-label">
                            <span class="board-hub-nav-icon" aria-hidden="true">⇄</span>
                            <span>共享项目</span>
                        </span>
                        <span class="board-hub-nav-caret" aria-hidden="true">▾</span>
                    </button>
                    <div class="board-hub-nav-group-body">
                        ${sharedOrganizationGroups
                            .map(
                                (group) => `
                            <a
                                class="board-hub-nav-subitem ${
                                    isSharedOrganizationNavActive(group, hub) ? "active" : ""
                                }"
                                href="${buildBoardHubHref("shared-org", group.org_name, {
                                    ownerTenantType: group.owner_tenant_type,
                                    ownerTenantId: group.owner_tenant_id,
                                    orgName: group.org_name,
                                })}"
                            >${escapeHtml(formatSharedOrgNavLabel(group))}</a>
                        `
                            )
                            .join("")}
                    </div>
                </div>`
                        : ""
                }
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
                : hub.scope === "shared-org"
                  ? "⇄"
                  : "▤";
    const sortBy = hub.sortBy;
    const canCreateBoard = hub.scope !== "shared-org";

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
                ${
                    canCreateBoard
                        ? `<button class="board-hub-tool-btn board-hub-tool-icon" id="createBoardHubBtn" type="button" title="新建看板">+</button>`
                        : ""
                }
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

function renderBoardHubCardOrg(board, hub = state.boardHub) {
    if (!shouldShowBoardHubCardOrg(board, hub)) {
        return "";
    }

    const org = formatBoardOrganization(board.organization);
    if (board.shared) {
        const owner = (board.owner_display_name || "").trim();
        const label = owner ? `${org} · ${owner}` : org;
        return `<div class="board-hub-card-head"><span class="board-hub-card-org is-shared-org" title="${escapeHtml(label)}">${escapeHtml(label)}</span></div>`;
    }

    const isPersonal = org === PERSONAL_BOARD_ORGANIZATION;
    return `<div class="board-hub-card-head"><span class="board-hub-card-org${isPersonal ? " is-personal-org" : ""}" title="${escapeHtml(org)}">${escapeHtml(org)}</span></div>`;
}

function shouldShowBoardHubCardOrg() {
    return true;
}

function renderBoardHubCard(board, hub = state.boardHub) {
    const sharedBadge = board.shared
        ? `<span class="board-share-badge">${board.share_permissions?.edit ? "可编辑分享" : "只读分享"}</span>`
        : "";
    const hoverActions = board.shared
        ? `<div class="board-hub-card-hover-actions"><span class="text-muted">${escapeHtml(board.owner_display_name || "好友分享")}</span></div>`
        : `<div class="board-hub-card-hover-actions">
                    <button class="btn btn-sm btn-light" data-action="edit-board" data-board-id="${board.id}" type="button">编辑</button>
                    <button class="btn btn-sm btn-outline-light" data-action="delete-board" data-board-id="${board.id}" type="button">删除</button>
                </div>`;
    return `
        <article class="board-hub-card ${board.shared ? "is-shared-board" : ""}" data-board-id="${board.id}"${board.shared ? ` data-owner-tenant-type="${escapeHtml(board.owner_tenant_type || "")}" data-owner-tenant-id="${escapeHtml(board.owner_tenant_id || "")}"` : ""}>
            <h3 class="board-hub-card-title">${escapeHtml(board.title)}${sharedBadge}</h3>
            ${renderBoardHubCardOrg(board, hub)}
            <div class="board-hub-card-footer">
                ${hoverActions}
                <div class="board-hub-card-actions">
                    ${board.shared ? "" : renderBoardStarButton(board.id)}
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
    if (hub.scope === "shared-org") {
        return `
            <div class="board-hub-empty">
                <h3>暂无共享看板</h3>
                <p>当其他用户向您分享看板后，会出现在左侧「共享项目」列表中。</p>
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
    const isSharedScope = hub.scope === "shared-org";
    const ownBoards = isSharedScope ? visibleBoards : visibleBoards.filter((board) => !board.shared);
    const sectionTitle = isSharedScope ? "共享看板" : ownBoards.length ? "我的看板" : "";

    appView.innerHTML = `
        <section class="board-hub-page">
            ${renderBoardHubSidebar(hub)}
            <div class="board-hub-main">
                ${renderBoardHubHeader(hub)}
                ${sectionTitle ? `<h3 class="board-hub-section-title">${sectionTitle}</h3>` : ""}
                <div class="board-hub-grid" id="boardGrid">
                    ${ownBoards.length ? ownBoards.map((board) => renderBoardHubCard(board, hub)).join("") : renderBoardHubEmpty(hub)}
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
            const ownerType = node.dataset.ownerTenantType || null;
            const ownerId = node.dataset.ownerTenantId || null;
            let href = `#/board/${node.dataset.boardId}`;
            if (ownerType && ownerId) {
                href += `?owner_tenant_type=${encodeURIComponent(ownerType)}&owner_tenant_id=${encodeURIComponent(ownerId)}`;
            }
            location.hash = href;
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
        node.addEventListener("click", (event) => {
            event.stopPropagation();
            promptDeleteBoard(node.dataset.boardId);
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

async function openBoard(boardId, cardId = null, ownerTenantType = null, ownerTenantId = null) {
    try {
        const boardMeta = findBoardById(boardId, ownerTenantType, ownerTenantId);
        if (boardMeta && !boardMeta.shared) {
            syncBoardHubForOrganization(boardMeta.organization);
        }
        const query =
            boardMeta?.shared && boardMeta.owner_tenant_type && boardMeta.owner_tenant_id
                ? `?owner_tenant_type=${encodeURIComponent(boardMeta.owner_tenant_type)}&owner_tenant_id=${encodeURIComponent(boardMeta.owner_tenant_id)}`
                : ownerTenantType && ownerTenantId
                  ? `?owner_tenant_type=${encodeURIComponent(ownerTenantType)}&owner_tenant_id=${encodeURIComponent(ownerTenantId)}`
                  : "";
        const data = await api(`/api/boards/${boardId}${query}`);
        state.currentBoardId = boardId;
        state.currentBoard = data;
        state.currentBoardAccess = data.shared
            ? {
                  shared: true,
                  permissions: data.share_permissions || { view: true, edit: false },
                  owner_tenant_type: data.owner_tenant_type,
                  owner_tenant_id: data.owner_tenant_id,
              }
            : null;
        state.currentBoardView = loadBoardViewPreference(boardId);
        clearError();
        renderBoardPage();
        await refreshBoardEditLocks(boardId, data.cards || []);
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
    if (settings) {
        const { organizations: _orgs, shared_boards: _sharedBoards, shared_org_index: _sharedOrgIndex, ...sharedSettings } = settings;
        state.settings = { ...state.settings, ...sharedSettings };
        if (state.authUser?.is_super_admin) {
            state.settings.organizations = _orgs || state.settings.organizations || [];
        }
        if (_sharedBoards) {
            state.settings.shared_boards = _sharedBoards;
        }
        if (_sharedOrgIndex) {
            state.settings.shared_org_index = _sharedOrgIndex;
        }
    }
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
                        ${!isBoardReadOnly() ? `<button class="btn btn-sm btn-light" id="shareCurrentBoardBtn" type="button">分享</button>` : ""}
                        ${!isBoardReadOnly() ? `<button class="btn btn-sm btn-light" id="editCurrentBoardBtn" type="button">编辑看板</button>` : `<span class="badge bg-secondary">只读分享</span>`}
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
                    ${isBoardReadOnly() ? "" : `<div class="add-list-column">
                        <button class="add-list-btn" data-action="add-list" id="addListBtn" type="button">+ 添加列表</button>
                    </div>`}
                </div>
            </div>
        </section>
    `;

    document.getElementById("editCurrentBoardBtn")?.addEventListener("click", () => {
        openBoardForm(board.id).catch((error) => showError(error.message || "打开看板表单失败"));
    });
    document.getElementById("shareCurrentBoardBtn")?.addEventListener("click", () => {
        openBoardShareModal().catch((error) => showError(error.message || "打开分享失败"));
    });
    bindBoardStatusDropdown();
    bindBoardOrgDropdown();
    bindBoardViewTabs();
    if (!isEditorView && !isBoardReadOnly()) {
        initSortables();
    }
}

function renderKanbanList(list, settings, { viewMode = "kanban" } = {}) {
    const readOnly = isBoardReadOnly();
    return `
        <section class="kanban-list" data-list-id="${list.id}">
            <div class="list-header">
                <div>
                    <h3>${escapeHtml(list.title)}<span class="list-count">${list.cards.length}</span></h3>
                </div>
                ${
                    readOnly
                        ? ""
                        : `<div class="list-menu-dropdown">
                    <button class="list-menu-btn" data-action="toggle-list-menu" data-list-id="${list.id}" type="button" title="列表菜单">☰</button>
                    <div class="list-menu-panel" data-list-menu="${list.id}">
                        <button class="list-menu-option" data-action="list-settings" data-list-id="${list.id}" type="button">设置</button>
                        <button class="list-menu-option list-menu-option-danger" data-action="delete-list" data-list-id="${list.id}" type="button">删除列表</button>
                    </div>
                </div>`
                }
            </div>
            <div class="list-cards" data-list-id="${list.id}">
                ${list.cards.map((card) => renderKanbanCard(card, settings, { viewMode })).join("")}
            </div>
            ${readOnly ? "" : `<div class="list-footer">
                <button class="add-card-btn" data-action="add-card" data-list-id="${list.id}" type="button">+ 添加卡片</button>
            </div>`}
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

    const listSettingsBtn = event.target.closest("[data-action='list-settings']");
    if (listSettingsBtn) {
        event.preventDefault();
        event.stopPropagation();
        closeAllListMenus();
        openListSettingsDialog(listSettingsBtn.dataset.listId);
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

function findListForCard(card) {
    if (!card) {
        return null;
    }
    if (card.list_id) {
        return findList(card.list_id);
    }
    for (const list of state.currentBoard?.lists || []) {
        if (list.cards?.some((item) => String(item.id) === String(card.id))) {
            return list;
        }
    }
    return null;
}

function resolveListCardSections(list) {
    const sections = list?.card_sections;
    return {
        show_checklist: sections?.show_checklist !== false,
        show_comments: sections?.show_comments !== false,
    };
}

function applyCardDetailSections(sections) {
    const showChecklist = sections?.show_checklist !== false;
    const showComments = sections?.show_comments !== false;
    document.getElementById("cardChecklistSection")?.classList.toggle("is-hidden", !showChecklist);
    document.getElementById("cardCommentsSection")?.classList.toggle("is-hidden", !showComments);
}

function openListSettingsDialog(listId) {
    const list = findList(listId);
    if (!list) {
        return;
    }
    editingListSettingsId = listId;
    const sections = resolveListCardSections(list);
    listSettingsTitleEl.textContent = "列表设置";
    listSettingsTitleInput.value = list.title || "";
    listSettingsShowChecklist.checked = sections.show_checklist;
    listSettingsShowComments.checked = sections.show_comments;
    listSettingsModal.show();
}

async function saveListSettings() {
    if (!editingListSettingsId || !state.currentBoardId) {
        return;
    }
    const title = listSettingsTitleInput.value.trim();
    if (!title) {
        showError("列表名称不能为空");
        return;
    }
    const payload = {
        title,
        card_sections: {
            show_checklist: listSettingsShowChecklist.checked,
            show_comments: listSettingsShowComments.checked,
        },
    };
    const result = await api(`/api/boards/${state.currentBoardId}/lists/${editingListSettingsId}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
    });
    const list = findList(editingListSettingsId);
    if (list) {
        list.title = result.item?.title || title;
        list.card_sections = result.item?.card_sections || payload.card_sections;
    }
    if (state.editingCard) {
        const cardList = findListForCard(state.editingCard);
        if (cardList && String(cardList.id) === String(editingListSettingsId)) {
            applyCardDetailSections(resolveListCardSections(list));
        }
    }
    editingListSettingsId = null;
    listSettingsModal.hide();
    showSuccess("列表设置已保存");
    await openBoard(state.currentBoardId);
}

function createDeleteMathChallenge() {
    const a = Math.floor(Math.random() * 9) + 1;
    const b = Math.floor(Math.random() * 9) + 1;
    return { question: `${a} + ${b} = ?`, answer: a + b };
}

function updateConfirmDeleteSubmitState() {
    if (confirmDeleteMathAnswer === null) {
        confirmDeleteSubmitBtn.disabled = false;
        return;
    }
    const value = Number.parseInt(confirmDeleteConfirmInput.value.trim(), 10);
    confirmDeleteSubmitBtn.disabled = value !== confirmDeleteMathAnswer;
}

function resetConfirmDeleteState() {
    confirmDeleteSubmitHandler = null;
    confirmDeleteMathAnswer = null;
    if (confirmDeleteConfirmWrap) {
        confirmDeleteConfirmWrap.hidden = true;
    }
    if (confirmDeleteConfirmInput) {
        confirmDeleteConfirmInput.value = "";
        confirmDeleteConfirmInput.oninput = null;
    }
    if (confirmDeleteMathQuestionEl) {
        confirmDeleteMathQuestionEl.textContent = "";
    }
    if (confirmDeleteSubmitBtn) {
        confirmDeleteSubmitBtn.disabled = false;
    }
}

function openConfirmDeleteDialog({ title, message, onSubmit, requireMathChallenge = true }) {
    confirmDeleteTitleEl.textContent = title;
    confirmDeleteMessageEl.innerHTML = message;
    confirmDeleteSubmitHandler = onSubmit;
    if (requireMathChallenge && confirmDeleteConfirmWrap && confirmDeleteConfirmInput && confirmDeleteMathQuestionEl) {
        const challenge = createDeleteMathChallenge();
        confirmDeleteMathAnswer = challenge.answer;
        confirmDeleteConfirmWrap.hidden = false;
        confirmDeleteMathQuestionEl.textContent = challenge.question;
        confirmDeleteConfirmInput.value = "";
        confirmDeleteSubmitBtn.disabled = true;
        confirmDeleteConfirmInput.oninput = updateConfirmDeleteSubmitState;
        confirmDeleteModal.show();
        window.setTimeout(() => confirmDeleteConfirmInput.focus(), 180);
        return;
    }
    confirmDeleteMathAnswer = null;
    if (confirmDeleteConfirmWrap) {
        confirmDeleteConfirmWrap.hidden = true;
    }
    if (confirmDeleteSubmitBtn) {
        confirmDeleteSubmitBtn.disabled = false;
    }
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
        if (confirmDeleteMathAnswer === null) {
            submitBtn.disabled = false;
        } else {
            updateConfirmDeleteSubmitState();
        }
    }
}

function promptDeleteBoard(boardId) {
    const board = findBoardById(boardId);
    if (!board) {
        showError("看板不存在或已删除");
        return;
    }
    openConfirmDeleteDialog({
        title: "删除看板",
        message: `确定要删除看板 <strong>${escapeHtml(board.title)}</strong> 吗？看板内的所有列表和卡片将一并删除。`,
        onSubmit: async () => {
            await api(`/api/boards/${boardId}`, { method: "DELETE" });
            if (String(state.currentBoardId) === String(boardId)) {
                state.currentBoardId = null;
                state.currentBoard = null;
                location.hash = "#/";
            }
            showSuccess("看板已删除");
            await loadBoards();
            renderBoardListContent();
        },
    });
}

function promptDeleteList(listId, { fromSettings = false } = {}) {
    const list = findList(listId);
    if (!list) {
        return;
    }
    if (fromSettings) {
        listSettingsModal.hide();
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
            editingListSettingsId = null;
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
    descriptionInteractionMode = "view";
    if (cardDescriptionModeSelect) {
        cardDescriptionModeSelect.value = pendingDescriptionMode;
    }
    applyDescriptionModeUI(pendingDescriptionMode);
    applyDescriptionInteractionUI("view");
    const cardList = findListForCard(card);
    applyCardDetailSections(resolveListCardSections(cardList));
    renderChecklist(card.checklist || []);
    renderComments(card.comments || []);
    commentInput.value = "";
    cardModal.show();
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
        body: JSON.stringify({
            content: nextContent,
            parent_id: parentCommentId,
            base_revision: cardRevisionValue(state.editingCard),
        }),
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
            body: JSON.stringify({
                content: nextContent,
                base_revision: cardRevisionValue(state.editingCard),
            }),
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
        {
            method: "DELETE",
            body: JSON.stringify({ base_revision: cardRevisionValue(state.editingCard) }),
        }
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
    const localSnapshot = {
        title: cardTitleInput.value.trim(),
        description: descriptionPayload.description,
        checklist: collectChecklistFromDom().filter((item) => item.text.trim()),
    };
    const payload = {
        title: localSnapshot.title,
        type: cardTypeSelect.value,
        description: localSnapshot.description,
        description_data: descriptionPayload.description_data,
        checklist: localSnapshot.checklist,
        base_revision: cardRevisionValue(state.editingCard),
    };

    const performSave = async (body) => {
        return api(`/api/boards/${state.currentBoardId}/cards/${state.editingCard.id}`, {
            method: "PATCH",
            body: JSON.stringify(body),
        });
    };

    try {
        await performSave(payload);
        cardModal.hide();
        showSuccess("卡片已保存");
        await openBoard(state.currentBoardId);
        return;
    } catch (saveError) {
        if (saveError.status !== 409 || saveError.data?.error !== "conflict") {
            showError(saveError.message || "保存失败");
            return;
        }
        const decision = await showCardConflictDialog(saveError.data, localSnapshot);
        if (decision.action === "cancel") {
            return;
        }
        if (decision.action === "reload") {
            const current = decision.current || saveError.data.current || {};
            state.editingCard = { ...state.editingCard, ...current };
            cardTitleInput.value = current.title || "";
            pendingDescriptionContent = current.description || "";
            pendingDescriptionMode = resolveCardDescriptionMode(current);
            if (cardDescriptionModeSelect) {
                cardDescriptionModeSelect.value = pendingDescriptionMode;
            }
            applyDescriptionModeUI(pendingDescriptionMode);
            renderChecklist(current.checklist || []);
            showError("已加载最新版本，请合并后再次保存");
            return;
        }
        if (decision.action === "force") {
            if (!confirm("确定用当前内容覆盖其他人的修改吗？")) {
                return;
            }
            try {
                await performSave({ ...payload, force: true });
                cardModal.hide();
                showSuccess("卡片已保存");
                await openBoard(state.currentBoardId);
            } catch (forceError) {
                showError(forceError.message || "覆盖保存失败");
            }
        }
    }
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
        body: JSON.stringify({
            content,
            base_revision: cardRevisionValue(state.editingCard),
        }),
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
    const organization = getBoardOrgValue();
    if (organization === null) {
        showError("请输入自定义组织名称");
        getBoardOrgElements().customInput?.focus();
        return;
    }

    const payload = {
        title: document.getElementById("boardTitleInput").value.trim(),
        status_id: boardStatusSelect.value,
        start_date: document.getElementById("boardStartInput").value,
        end_date: document.getElementById("boardEndInput").value,
        organization,
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
            await loadSettings();
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
        await loadSettings();
        await loadBoards();
        const created = state.boards.find((item) => String(item.id) === String(result.item.id));
        if (!created) {
            showError("看板已提交但未写入存储，请重启服务后重试");
            renderBoardList();
            return;
        }
        showSuccess("看板已创建");
        syncBoardHubForOrganization(organization);
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
    const headers = {
        "Content-Type": "application/json",
        ...(options.headers || {}),
    };
    if (state.currentBoardAccess?.shared && String(url).includes("/api/boards/")) {
        headers["X-Board-Owner-Type"] = state.currentBoardAccess.owner_tenant_type;
        headers["X-Board-Owner-Id"] = state.currentBoardAccess.owner_tenant_id;
    }
    const response = await fetch(url, {
        credentials: "same-origin",
        headers,
        ...options,
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(data.message || "请求失败");
        error.status = response.status;
        error.data = data;
        throw error;
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
