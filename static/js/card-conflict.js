/** 卡片保存冲突弹窗 */

function cardRevisionValue(card) {
    if (!card || card.revision == null) {
        return 0;
    }
    const value = Number(card.revision);
    return Number.isFinite(value) ? value : 0;
}

function summarizeCardConflict(current, local) {
    const fields = [];
    if ((current?.title || "") !== (local?.title || "")) {
        fields.push("标题");
    }
    if ((current?.description || "") !== (local?.description || "")) {
        fields.push("描述");
    }
    const currentChecklist = JSON.stringify(current?.checklist || []);
    const localChecklist = JSON.stringify(local?.checklist || []);
    if (currentChecklist !== localChecklist) {
        fields.push("检查清单");
    }
    return fields.length ? fields.join("、") : "卡片内容";
}

function ensureCardConflictModal() {
    let modal = document.getElementById("cardConflictModal");
    if (modal) {
        return modal;
    }

    document.body.insertAdjacentHTML(
        "beforeend",
        `
        <div class="modal fade" id="cardConflictModal" tabindex="-1" aria-hidden="true">
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content">
                    <div class="modal-header">
                        <h5 class="modal-title">保存冲突</h5>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="关闭"></button>
                    </div>
                    <div class="modal-body">
                        <p id="cardConflictMessage" class="mb-2">卡片已被其他人更新。</p>
                        <p id="cardConflictFields" class="text-muted small mb-0"></p>
                    </div>
                    <div class="modal-footer">
                        <button type="button" class="btn btn-outline-secondary" data-action="cancel">取消</button>
                        <button type="button" class="btn btn-primary" data-action="reload">查看最新并合并</button>
                        <button type="button" class="btn btn-danger" data-action="force">仍要覆盖</button>
                    </div>
                </div>
            </div>
        </div>
        `
    );
    modal = document.getElementById("cardConflictModal");
    return modal;
}

function showCardConflictDialog(conflictData, localSnapshot) {
    const modalElement = ensureCardConflictModal();
    const bsModal = bootstrap.Modal.getOrCreateInstance(modalElement);
    const current = conflictData?.current || {};
    const changed = summarizeCardConflict(current, localSnapshot);
    document.getElementById("cardConflictMessage").textContent =
        conflictData?.message || "在你编辑期间，其他人已更新了此卡片。";
    document.getElementById("cardConflictFields").textContent = `冲突字段：${changed}`;

    return new Promise((resolve) => {
        const cleanup = () => {
            modalElement.querySelector('[data-action="cancel"]').removeEventListener("click", onCancel);
            modalElement.querySelector('[data-action="reload"]').removeEventListener("click", onReload);
            modalElement.querySelector('[data-action="force"]').removeEventListener("click", onForce);
            modalElement.removeEventListener("hidden.bs.modal", onHidden);
        };

        const finish = (action) => {
            cleanup();
            bsModal.hide();
            resolve({ action, current });
        };

        const onCancel = () => finish("cancel");
        const onReload = () => finish("reload");
        const onForce = () => finish("force");
        const onHidden = () => {
            cleanup();
            resolve({ action: "cancel", current });
        };

        modalElement.querySelector('[data-action="cancel"]').addEventListener("click", onCancel);
        modalElement.querySelector('[data-action="reload"]').addEventListener("click", onReload);
        modalElement.querySelector('[data-action="force"]').addEventListener("click", onForce);
        modalElement.addEventListener("hidden.bs.modal", onHidden, { once: true });
        bsModal.show();
    });
}

function showEditorLockDialog(holder, editorLabel) {
    const name = holder?.display_name || "其他用户";
    const since = holder?.acquired_at ? `（自 ${holder.acquired_at}）` : "";
    window.alert(`${name} 正在编辑${editorLabel || "此内容"}${since}，请稍后再试。`);
}

function editLockStorageKey(boardId, cardId, editorKey) {
    return `boardflow:edit-lock:${boardId}:${cardId}:${editorKey}`;
}

function readStoredEditLock(boardId, cardId, editorKey) {
    try {
        const raw = sessionStorage.getItem(editLockStorageKey(boardId, cardId, editorKey));
        return raw ? JSON.parse(raw) : null;
    } catch (_error) {
        return null;
    }
}

function writeStoredEditLock(boardId, cardId, editorKey, payload) {
    sessionStorage.setItem(editLockStorageKey(boardId, cardId, editorKey), JSON.stringify(payload));
}

function clearStoredEditLock(boardId, cardId, editorKey) {
    sessionStorage.removeItem(editLockStorageKey(boardId, cardId, editorKey));
}

function buildBoardOwnerHeaders() {
    if (!state.currentBoardAccess?.shared) {
        return {};
    }
    return {
        "X-Board-Owner-Type": state.currentBoardAccess.owner_tenant_type,
        "X-Board-Owner-Id": state.currentBoardAccess.owner_tenant_id,
    };
}

async function fetchBoardApi(url, options = {}) {
    const headers = {
        "Content-Type": "application/json",
        ...buildBoardOwnerHeaders(),
        ...(options.headers || {}),
    };
    const response = await fetch(url, {
        credentials: "same-origin",
        ...options,
        headers,
    });
    const data = await response.json().catch(() => ({}));
    return { ok: response.ok, status: response.status, data };
}

async function acquireEditorLockBeforeOpen(boardId, cardId, editorKey, editorLabel) {
    const collab = state.settings?.collaboration;
    if (!collab?.enabled || !collab?.editor_exclusive_lock) {
        return true;
    }
    if (!(collab.locked_editors || []).includes(editorKey)) {
        return true;
    }

    const clientId = readStoredEditLock(boardId, cardId, editorKey)?.client_id || crypto.randomUUID();
    const result = await fetchBoardApi(`/api/boards/${boardId}/cards/${cardId}/${editorKey}/lock`, {
        method: "POST",
        body: JSON.stringify({ client_id: clientId }),
    });
    if (result.ok) {
        writeStoredEditLock(boardId, cardId, editorKey, {
            token: result.data.token,
            client_id: result.data.client_id || clientId,
            revision: result.data.revision ?? 0,
            heartbeat_interval_sec: result.data.heartbeat_interval_sec || 60,
        });
        return true;
    }
    if (result.status === 409 && result.data?.error === "locked") {
        showEditorLockDialog(result.data.holder, editorLabel);
        return false;
    }
    throw new Error(result.data.message || "无法获取编辑锁");
}

async function refreshBoardEditLocks(boardId, cards) {
    const collab = state.settings?.collaboration;
    if (!collab?.enabled || !collab?.editor_exclusive_lock || !Array.isArray(cards) || !cards.length) {
        state.boardEditLocks = {};
        return;
    }
    const cardIds = cards.map((card) => card.id).filter(Boolean);
    if (!cardIds.length) {
        state.boardEditLocks = {};
        return;
    }
    const query = encodeURIComponent(cardIds.join(","));
    const result = await fetchBoardApi(`/api/boards/${boardId}/edit-locks?card_ids=${query}`);
    if (!result.ok) {
        return;
    }
    const map = {};
    for (const item of result.data.items || []) {
        const key = `${item.card_id}:${item.scope}`;
        map[key] = item;
    }
    state.boardEditLocks = map;
}

function isCardEditorLocked(cardId, editorKey) {
    const item = state.boardEditLocks?.[`${cardId}:${editorKey}`];
    return Boolean(item?.holder);
}

function cardEditorLockHolder(cardId, editorKey) {
    return state.boardEditLocks?.[`${cardId}:${editorKey}`]?.holder || null;
}
