import { useCallback, useEffect, useRef, useState } from "react";
import {
  createEditorApi,
  EditorShell,
  EditorTopbar,
  normalizeReturnHref,
  readEditorContext,
  useAutoSave,
} from "@boardflow/editor-shell";

const { boardId, cardId, cardTitle, returnUrl } = readEditorContext();
const backHref = normalizeReturnHref(returnUrl, boardId);
const tableApi = createEditorApi(boardId, cardId, "table", "table_data");

function getLuckysheet() {
  return window.luckysheet;
}

function waitForLuckysheet(timeoutMs = 15000) {
  return new Promise((resolve, reject) => {
    const startedAt = Date.now();

    const check = () => {
      const luckysheet = getLuckysheet();
      if (luckysheet && typeof luckysheet.create === "function") {
        resolve(luckysheet);
        return;
      }
      if (Date.now() - startedAt > timeoutMs) {
        reject(new Error("Luckysheet 脚本未加载，请刷新页面重试"));
        return;
      }
      window.requestAnimationFrame(check);
    };

    check();
  });
}

function buildInitialSheetData(title) {
  const sheetName = (title || "表格").slice(0, 31);
  return [
    {
      name: sheetName,
      color: "",
      status: 1,
      order: 0,
      index: 0,
      celldata: [],
      config: {},
      row: 84,
      column: 60,
    },
  ];
}

function normalizeSheetData(data, title) {
  if (Array.isArray(data) && data.length) {
    return data;
  }
  return buildInitialSheetData(title);
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [saveHint, setSaveHint] = useState("自动保存");
  const [isSaving, setIsSaving] = useState(false);
  const hostRef = useRef(null);
  const mountedRef = useRef(false);
  const initialDataRef = useRef(null);
  const scheduleSaveRef = useRef(() => {});

  const persistTable = useCallback(async () => {
    const luckysheet = getLuckysheet();
    if (!mountedRef.current || !luckysheet || typeof luckysheet.getAllSheets !== "function") {
      return;
    }
    await tableApi.save(luckysheet.getAllSheets());
  }, []);

  const { flushSave, scheduleSave, clearTimer } = useAutoSave({
    onSave: persistTable,
    onHintChange: setSaveHint,
  });

  scheduleSaveRef.current = scheduleSave;

  useEffect(() => {
    tableApi
      .load()
      .then((data) => {
        initialDataRef.current = data;
        setReady(true);
      })
      .catch((loadError) => setError(loadError.message || "加载失败"));
  }, []);

  useEffect(() => {
    return tableApi.saveOnPageHide(() => {
      const luckysheet = getLuckysheet();
      if (!mountedRef.current || !luckysheet || typeof luckysheet.getAllSheets !== "function") {
        return null;
      }
      return luckysheet.getAllSheets();
    });
  }, []);

  useEffect(() => {
    if (!ready || !hostRef.current) {
      return undefined;
    }

    let cancelled = false;
    const host = hostRef.current;
    host.id = "luckysheet";

    waitForLuckysheet()
      .then((luckysheet) => {
        if (cancelled || !hostRef.current) {
          return;
        }

        if (typeof luckysheet.destroy === "function") {
          luckysheet.destroy();
        }

        luckysheet.create({
          container: "luckysheet",
          lang: "zh",
          showinfobar: false,
          showsheetbar: true,
          showstatisticBar: true,
          allowEdit: true,
          data: normalizeSheetData(initialDataRef.current, cardTitle),
          hook: {
            updated: () => scheduleSaveRef.current(),
            cellUpdated: () => scheduleSaveRef.current(),
            sheetActivate: () => scheduleSaveRef.current(),
          },
        });

        mountedRef.current = true;
      })
      .catch((initError) => {
        if (!cancelled) {
          setError(initError.message || "表格初始化失败");
        }
      });

    return () => {
      cancelled = true;
      mountedRef.current = false;
      clearTimer();
      const luckysheet = getLuckysheet();
      if (luckysheet && typeof luckysheet.destroy === "function") {
        luckysheet.destroy();
      }
      if (hostRef.current) {
        hostRef.current.innerHTML = "";
      }
    };
  }, [ready, clearTimer, cardTitle]);

  const handleBack = async (event) => {
    event.preventDefault();
    if (isSaving) {
      return;
    }
    setIsSaving(true);
    setSaveHint("保存中...");
    try {
      await flushSave();
      setSaveHint("已保存，正在返回...");
      window.location.href = backHref;
    } catch (saveError) {
      setSaveHint(saveError.message || "保存失败");
      setIsSaving(false);
    }
  };

  if (error) {
    return <div className="editor-error">{error}</div>;
  }

  if (!ready) {
    return <div className="editor-loading">表格加载中...</div>;
  }

  return (
    <EditorShell
      className="table-stage editor-stage"
      topbar={
        <EditorTopbar
          title={cardTitle || "表格"}
          saveHint={saveHint}
          isSaving={isSaving}
          onBack={handleBack}
        />
      }
    >
      <div ref={hostRef} className="table-sheet-host" />
    </EditorShell>
  );
}
