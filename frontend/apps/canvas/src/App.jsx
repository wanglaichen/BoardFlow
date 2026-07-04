import { useCallback, useEffect, useRef, useState } from "react";
import { Tldraw, getSnapshot, loadSnapshot, useTldrawUser } from "tldraw";
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
const canvasApi = createEditorApi(boardId, cardId, "canvas", "canvas_data");

function updateGroupState(editor, setCanGroup, setCanUngroup) {
  const ids = editor.getSelectedShapeIds();
  const hasGroup = ids.some((id) => editor.getShape(id)?.type === "group");
  setCanGroup(ids.length >= 2 && editor.isIn("select"));
  setCanUngroup(hasGroup && editor.isIn("select"));
}

export default function App() {
  const [ready, setReady] = useState(false);
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState("");
  const [saveHint, setSaveHint] = useState("自动保存");
  const [isSaving, setIsSaving] = useState(false);
  const [canGroup, setCanGroup] = useState(false);
  const [canUngroup, setCanUngroup] = useState(false);
  const editorRef = useRef(null);
  const user = useTldrawUser({ userPreferences: { locale: "zh-cn" } });

  const persistCanvas = useCallback(async () => {
    if (!editorRef.current) {
      return;
    }
    await canvasApi.save(getSnapshot(editorRef.current.store));
  }, []);

  const { flushSave, scheduleSave, clearTimer } = useAutoSave({
    onSave: persistCanvas,
    onHintChange: setSaveHint,
  });

  useEffect(() => {
    canvasApi
      .load()
      .then((data) => {
        setSnapshot(data);
        setReady(true);
      })
      .catch((loadError) => setError(loadError.message || "加载失败"));
  }, []);

  useEffect(() => {
    return canvasApi.saveOnPageHide(() => {
      if (!editorRef.current) {
        return null;
      }
      return getSnapshot(editorRef.current.store);
    });
  }, []);

  const handleMount = useCallback(
    (editor) => {
      editorRef.current = editor;

      if (snapshot) {
        try {
          loadSnapshot(editor.store, snapshot);
        } catch (loadError) {
          console.warn("loadSnapshot failed", loadError);
        }
      }

      const syncGroupState = () => updateGroupState(editor, setCanGroup, setCanUngroup);
      syncGroupState();

      const cleanupDocument = editor.store.listen(scheduleSave, { scope: "document" });
      const cleanupSession = editor.store.listen(syncGroupState, { scope: "session" });
      return () => {
        clearTimer();
        cleanupDocument();
        cleanupSession();
        editorRef.current = null;
        setCanGroup(false);
        setCanUngroup(false);
      };
    },
    [snapshot, scheduleSave, clearTimer]
  );

  const handleGroup = () => {
    const editor = editorRef.current;
    if (!editor || !canGroup) {
      return;
    }
    editor.markHistoryStoppingPoint("group");
    editor.groupShapes(editor.getSelectedShapeIds());
  };

  const handleUngroup = () => {
    const editor = editorRef.current;
    if (!editor || !canUngroup) {
      return;
    }
    editor.markHistoryStoppingPoint("ungroup");
    editor.ungroupShapes(editor.getSelectedShapeIds());
  };

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
    return <div className="editor-loading">画布加载中...</div>;
  }

  return (
    <EditorShell
      className="canvas-stage"
      topbar={
        <EditorTopbar
          title={cardTitle || "画布"}
          saveHint={saveHint}
          isSaving={isSaving}
          onBack={handleBack}
          actions={
            <>
              <button
                type="button"
                className="editor-action-btn"
                onClick={handleGroup}
                disabled={!canGroup}
                title="组合选中图形 (Ctrl+G)"
              >
                组合
              </button>
              <button
                type="button"
                className="editor-action-btn"
                onClick={handleUngroup}
                disabled={!canUngroup}
                title="取消组合 (Ctrl+Shift+G)"
              >
                取消组合
              </button>
            </>
          }
        />
      }
    >
      <Tldraw user={user} onMount={handleMount} />
    </EditorShell>
  );
}
