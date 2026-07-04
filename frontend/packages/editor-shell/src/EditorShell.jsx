export default function EditorShell({ className = "", topbar, children }) {
  return (
    <div className={`editor-shell ${className}`.trim()}>
      {topbar}
      {children}
    </div>
  );
}
