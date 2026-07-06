export function readEditorContext() {
  const { boardId, cardId, cardTitle, returnUrl, editorKey, ownerTenantType, ownerTenantId } =
    document.body.dataset;
  return {
    boardId,
    cardId,
    cardTitle: cardTitle || "",
    returnUrl: returnUrl || `#/board/${boardId}`,
    editorKey: editorKey || "",
    ownerTenantType: ownerTenantType || "",
    ownerTenantId: ownerTenantId || "",
  };
}

export function normalizeReturnHref(returnUrl, boardId) {
  if (!returnUrl) {
    return `/#/board/${boardId}`;
  }
  if (returnUrl.startsWith("http://") || returnUrl.startsWith("https://")) {
    return returnUrl;
  }
  if (returnUrl.startsWith("#")) {
    return `/${returnUrl}`;
  }
  if (returnUrl.startsWith("/#")) {
    return returnUrl;
  }
  return `/#${returnUrl.replace(/^\//, "")}`;
}

function readOwnerHeaders(context) {
  const params = new URLSearchParams(window.location.search);
  const ownerType = params.get("owner_tenant_type") || context.ownerTenantType;
  const ownerId = params.get("owner_tenant_id") || context.ownerTenantId;
  if (ownerType && ownerId) {
    return {
      "X-Board-Owner-Type": ownerType,
      "X-Board-Owner-Id": ownerId,
    };
  }
  return {};
}

export function createEditorApi(boardId, cardId, editorKey, payloadField, options = {}) {
  const basePath = `/api/boards/${boardId}/cards/${cardId}/${editorKey}`;
  const context = readEditorContext();
  const getLockToken = options.getLockToken || (() => "");
  const getRevision = options.getRevision || (() => 0);
  const onRevisionChange = options.onRevisionChange;

  const buildHeaders = () => {
    const headers = {
      "Content-Type": "application/json",
      ...readOwnerHeaders(context),
    };
    const token = getLockToken();
    if (token) {
      headers["X-Edit-Lock-Token"] = token;
    }
    return headers;
  };

  const parseResponse = async (response) => {
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(data.message || `请求失败 (${response.status})`);
      error.status = response.status;
      error.data = data;
      throw error;
    }
    if (data.revision != null && onRevisionChange) {
      onRevisionChange(data.revision);
    }
    return data;
  };

  return {
    async load() {
      const response = await fetch(basePath, {
        credentials: "same-origin",
        headers: readOwnerHeaders(context),
      });
      const data = await parseResponse(response);
      if (data.revision != null && onRevisionChange) {
        onRevisionChange(data.revision);
      }
      return data[payloadField] ?? null;
    },
    async save(payload, saveOptions = {}) {
      const response = await fetch(basePath, {
        method: "PUT",
        credentials: "same-origin",
        headers: buildHeaders(),
        body: JSON.stringify({
          [payloadField]: payload,
          base_revision: saveOptions.base_revision ?? getRevision(),
          force: Boolean(saveOptions.force),
        }),
      });
      await parseResponse(response);
    },
    saveOnPageHide(getPayload) {
      const handler = () => {
        const payload = getPayload();
        if (payload == null) {
          return;
        }
        fetch(basePath, {
          method: "PUT",
          credentials: "same-origin",
          headers: buildHeaders(),
          body: JSON.stringify({
            [payloadField]: payload,
            base_revision: getRevision(),
          }),
          keepalive: true,
        }).catch(() => {});
      };
      window.addEventListener("pagehide", handler);
      return () => window.removeEventListener("pagehide", handler);
    },
  };
}
