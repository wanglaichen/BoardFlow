export function readEditorContext() {
  const { boardId, cardId, cardTitle, returnUrl } = document.body.dataset;
  return {
    boardId,
    cardId,
    cardTitle: cardTitle || "",
    returnUrl: returnUrl || `#/board/${boardId}`,
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

export function createEditorApi(boardId, cardId, editorKey, payloadField) {
  const basePath = `/api/boards/${boardId}/cards/${cardId}/${editorKey}`;

  return {
    async load() {
      const response = await fetch(basePath);
      if (!response.ok) {
        throw new Error(`加载失败 (${response.status})`);
      }
      const data = await response.json();
      return data[payloadField] ?? null;
    },
    async save(payload) {
      const response = await fetch(basePath, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [payloadField]: payload }),
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.message || "保存失败");
      }
    },
    saveOnPageHide(getPayload) {
      const handler = () => {
        const payload = getPayload();
        if (payload == null) {
          return;
        }
        fetch(basePath, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ [payloadField]: payload }),
          keepalive: true,
        }).catch(() => {});
      };
      window.addEventListener("pagehide", handler);
      return () => window.removeEventListener("pagehide", handler);
    },
  };
}
