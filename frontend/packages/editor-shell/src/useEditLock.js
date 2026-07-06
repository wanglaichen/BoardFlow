import { useCallback, useEffect, useRef, useState } from "react";
import { readEditorContext } from "./editorContext.js";

function lockStorageKey(boardId, cardId, editorKey) {
  return `boardflow:edit-lock:${boardId}:${cardId}:${editorKey}`;
}

function readStoredLock(boardId, cardId, editorKey) {
  try {
    const raw = sessionStorage.getItem(lockStorageKey(boardId, cardId, editorKey));
    return raw ? JSON.parse(raw) : null;
  } catch (_error) {
    return null;
  }
}

function writeStoredLock(boardId, cardId, editorKey, payload) {
  sessionStorage.setItem(lockStorageKey(boardId, cardId, editorKey), JSON.stringify(payload));
}

function clearStoredLock(boardId, cardId, editorKey) {
  sessionStorage.removeItem(lockStorageKey(boardId, cardId, editorKey));
}

function readOwnerHeaders() {
  const params = new URLSearchParams(window.location.search);
  const ownerType = params.get("owner_tenant_type") || document.body.dataset.ownerTenantType;
  const ownerId = params.get("owner_tenant_id") || document.body.dataset.ownerTenantId;
  if (ownerType && ownerId) {
    return {
      "X-Board-Owner-Type": ownerType,
      "X-Board-Owner-Id": ownerId,
    };
  }
  return {};
}

async function lockRequest(path, { method = "GET", token = "", body = null } = {}) {
  const headers = {
    "Content-Type": "application/json",
    ...readOwnerHeaders(),
  };
  if (token) {
    headers["X-Edit-Lock-Token"] = token;
  }
  const response = await fetch(path, {
    method,
    credentials: "same-origin",
    headers,
    body: body == null ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, data };
}

export function useEditLock(editorKey) {
  const { boardId, cardId } = readEditorContext();
  const [status, setStatus] = useState("pending");
  const [error, setError] = useState("");
  const tokenRef = useRef("");
  const revisionRef = useRef(0);
  const heartbeatMsRef = useRef(60000);
  const clientIdRef = useRef(crypto.randomUUID());
  const lockPath = `/api/boards/${boardId}/cards/${cardId}/${editorKey}/lock`;

  const releaseLock = useCallback(async () => {
    const token = tokenRef.current;
    if (!token) {
      return;
    }
    await lockRequest(lockPath, { method: "DELETE", token }).catch(() => {});
    clearStoredLock(boardId, cardId, editorKey);
    tokenRef.current = "";
  }, [boardId, cardId, editorKey, lockPath]);

  useEffect(() => {
    let cancelled = false;
    let timerId = 0;

    const applyLock = (payload) => {
      tokenRef.current = payload.token || "";
      revisionRef.current = Number(payload.revision || 0);
      heartbeatMsRef.current = Math.max(15000, Number(payload.heartbeat_interval_sec || 60) * 1000);
      writeStoredLock(boardId, cardId, editorKey, {
        token: tokenRef.current,
        client_id: clientIdRef.current,
        revision: revisionRef.current,
        heartbeat_interval_sec: payload.heartbeat_interval_sec || 60,
      });
      setStatus("ready");
    };

    const startHeartbeat = () => {
      window.clearInterval(timerId);
      timerId = window.setInterval(async () => {
        if (!tokenRef.current) {
          return;
        }
        const result = await lockRequest(lockPath, {
          method: "PUT",
          token: tokenRef.current,
        });
        if (!result.ok) {
          setError(result.data.message || "编辑锁已失效，请返回后重新打开");
          setStatus("error");
        }
      }, heartbeatMsRef.current);
    };

    const bootstrap = async () => {
      const stored = readStoredLock(boardId, cardId, editorKey);
      if (stored?.client_id) {
        clientIdRef.current = stored.client_id;
      }
      if (stored?.token) {
        applyLock(stored);
        startHeartbeat();
        return;
      }

      const result = await lockRequest(lockPath, {
        method: "POST",
        body: { client_id: clientIdRef.current },
      });
      if (cancelled) {
        return;
      }
      if (result.ok) {
        if (result.data.disabled) {
          setStatus("ready");
          return;
        }
        applyLock(result.data);
        startHeartbeat();
        return;
      }
      if (result.status === 409) {
        const holder = result.data?.holder?.display_name || "其他用户";
        setError(`${holder} 正在编辑，请稍后再试`);
        setStatus("error");
        return;
      }
      setError(result.data.message || "无法获取编辑锁");
      setStatus("error");
    };

    bootstrap();

    const onPageHide = () => {
      const token = tokenRef.current;
      if (!token) {
        return;
      }
      fetch(lockPath, {
        method: "DELETE",
        credentials: "same-origin",
        headers: {
          "X-Edit-Lock-Token": token,
          ...readOwnerHeaders(),
        },
        keepalive: true,
      }).catch(() => {});
    };

    window.addEventListener("pagehide", onPageHide);

    return () => {
      cancelled = true;
      window.clearInterval(timerId);
      window.removeEventListener("pagehide", onPageHide);
      releaseLock();
    };
  }, [boardId, cardId, editorKey, lockPath, releaseLock]);

  return {
    status,
    error,
    lockToken: tokenRef,
    revisionRef,
    setRevision: (value) => {
      revisionRef.current = Number(value || 0);
    },
  };
}
