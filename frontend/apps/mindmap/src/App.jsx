import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MindElixir from "mind-elixir";
import { zh_CN } from "mind-elixir/i18n";
import {
  createEditorApi,
  EditorShell,
  EditorTopbar,
  normalizeReturnHref,
  readEditorContext,
  useAutoSave,
  useEditLock,
} from "@boardflow/editor-shell";

const { boardId, cardId, cardTitle, returnUrl } = readEditorContext();
const backHref = normalizeReturnHref(returnUrl, boardId);

function buildInitialData(topic) {
  const data = MindElixir.new(topic);
  if (data?.nodeData) {
    data.nodeData.topic = topic;
  }
  return data;
}

export default function App() {
  const { status: lockStatus, error: lockError, lockToken, revisionRef, setRevision } = useEditLock("mindmap");
  const mindmapApi = useMemo(
    () =>
      createEditorApi(boardId, cardId, "mindmap", "mindmap_data", {
        getLockToken: () => lockToken.current,
        getRevision: () => revisionRef.current,
        onRevisionChange: setRevision,
      }),
    [lockToken, revisionRef, setRevision]
  );

  const [ready, setReady] = useState(false);
  const [savedData, setSavedData] = useState(null);
  const [error, setError] = useState("");
  const [saveHint, setSaveHint] = useState("自动保存");
  const [isSaving, setIsSaving] = useState(false);
  const containerRef = useRef(null);
  const mindRef = useRef(null);

  const persistMindmap = useCallback(async () => {
    if (!mindRef.current) {
      return;
    }
    await mindmapApi.save(mindRef.current.getData());
  }, [mindmapApi]);

  const { flushSave, scheduleSave, clearTimer } = useAutoSave({
    onSave: persistMindmap,
    onHintChange: setSaveHint,
  });

  useEffect(() => {
    if (lockStatus !== "ready") {
      return undefined;
    }
    mindmapApi
      .load()
      .then((data) => {
        setSavedData(data);
        setReady(true);
      })
      .catch((loadError) => setError(loadError.message || "加载失败"));
    return undefined;
  }, [lockStatus, mindmapApi]);

  useEffect(() => {
    if (lockStatus !== "ready") {
      return undefined;
    }
    return mindmapApi.saveOnPageHide(() => {
      if (!mindRef.current) {
        return null;
      }
      return mindRef.current.getData();
    });
  }, [lockStatus, mindmapApi]);

  useEffect(() => {
    if (!ready || !containerRef.current) {
      return undefined;
    }

    const mind = new MindElixir({
      el: containerRef.current,
      direction: MindElixir.LEFT,
      draggable: true,
      toolBar: true,
      keypress: true,
      contextMenu: {
        locale: zh_CN,
        focus: true,
        link: true,
      },
    });

    mind.init(savedData || buildInitialData(cardTitle || "思维导图"));
    mindRef.current = mind;
    mind.bus.addListener("operation", scheduleSave);

    return () => {
      clearTimer();
      mind.bus.removeListener("operation", scheduleSave);
      mindRef.current = null;
    };
  }, [ready, savedData, scheduleSave, clearTimer, cardTitle]);

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

  if (lockStatus === "pending") {
    return <div className="editor-loading">正在获取编辑锁...</div>;
  }

  if (lockStatus === "error") {
    return (
      <div className="editor-error">
        <p>{lockError || "无法进入编辑模式"}</p>
        <a href={backHref}>返回看板</a>
      </div>
    );
  }

  if (error) {
    return <div className="editor-error">{error}</div>;
  }

  if (!ready) {
    return <div className="editor-loading">思维导图加载中...</div>;
  }

  return (
    <EditorShell
      className="mindmap-stage editor-stage"
      topbar={
        <EditorTopbar
          title={cardTitle || "思维导图"}
          saveHint={saveHint}
          isSaving={isSaving}
          onBack={handleBack}
        />
      }
    >
      <div ref={containerRef} className="map-container" />
    </EditorShell>
  );
}
