"use client";

import { useEffect } from "react";

export function UnsavedChangesGuard({ enabled }: { enabled: boolean }) {
  useEffect(() => {
    if (!enabled) return;
    function handleBeforeUnload(event: BeforeUnloadEvent) {
      event.preventDefault();
      event.returnValue = "";
    }
    window.addEventListener("beforeunload", handleBeforeUnload);
    return () => window.removeEventListener("beforeunload", handleBeforeUnload);
  }, [enabled]);
  return null;
}
