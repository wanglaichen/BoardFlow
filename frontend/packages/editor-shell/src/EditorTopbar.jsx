export default function EditorTopbar({ title, saveHint, isSaving, onBack, actions = null }) {
  return (
    <div className="editor-topbar">
      <button type="button" className="editor-back-btn" onClick={onBack} disabled={isSaving}>
        ← 返回看板
      </button>
      <strong>{title}</strong>
      {actions ? <div className="editor-topbar-actions">{actions}</div> : null}
      <span className="editor-save-hint">{saveHint}</span>
    </div>
  );
}
