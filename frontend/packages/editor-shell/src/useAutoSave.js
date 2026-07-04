import { useCallback, useRef } from "react";

export function useAutoSave({ onSave, debounceMs = 700, onHintChange }) {
  const timerRef = useRef(null);

  const flushSave = useCallback(async () => {
    window.clearTimeout(timerRef.current);
    await onSave();
  }, [onSave]);

  const scheduleSave = useCallback(() => {
    window.clearTimeout(timerRef.current);
    onHintChange?.("保存中...");
    timerRef.current = window.setTimeout(async () => {
      try {
        await onSave();
        onHintChange?.("已自动保存");
      } catch (error) {
        onHintChange?.(error.message || "保存失败");
      }
    }, debounceMs);
  }, [debounceMs, onHintChange, onSave]);

  const clearTimer = useCallback(() => {
    window.clearTimeout(timerRef.current);
  }, []);

  return { flushSave, scheduleSave, clearTimer };
}
