"use client";

import { useEffect, useRef } from "react";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

export const CAPTURE_INBOX_PROMOTE_TOP_BATCHES = [5, 10, 20] as const;

type CaptureInboxPromoteSplitButtonProps = {
  onOpenReady: () => void;
  onPromoteAllReady: () => void;
  onPromoteTop: (limit: number) => void;
  promoting: boolean;
  readyCount: number;
  readyViewActive: boolean;
  selectedSession: boolean;
  visibleCount: number;
  working: boolean;
};

function MenuCaretIcon() {
  return (
    <span aria-hidden="true" className="capture-inbox-hero-promote-split__caret">
      <svg fill="none" viewBox="0 0 12 12" xmlns="http://www.w3.org/2000/svg">
        <path d="M2.5 4.25 6 7.75l3.5-3.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.4" />
      </svg>
    </span>
  );
}

export function CaptureInboxPromoteSplitButton({
  onOpenReady,
  onPromoteAllReady,
  onPromoteTop,
  promoting,
  readyCount,
  readyViewActive,
  selectedSession,
  visibleCount,
  working
}: CaptureInboxPromoteSplitButtonProps) {
  const menuRef = useRef<HTMLDetailsElement>(null);
  const mainDisabled = !selectedSession || working || readyCount === 0;
  const menuDisabled = !selectedSession || working;
  const topDisabled = working || visibleCount === 0;

  useEffect(() => {
    function handlePointerDown(event: PointerEvent) {
      const menu = menuRef.current;
      if (!menu || !(event.target instanceof Node) || menu.contains(event.target)) return;
      menu.removeAttribute("open");
    }

    document.addEventListener("pointerdown", handlePointerDown);
    return () => document.removeEventListener("pointerdown", handlePointerDown);
  }, []);

  function closeMenu() {
    menuRef.current?.removeAttribute("open");
  }

  if (!readyViewActive) {
    return (
      <div className="capture-inbox-hero-promote-split">
        <button
          className="capture-inbox-hero-promote-split__main is-open-ready"
          disabled={!selectedSession || working || readyCount === 0}
          onClick={onOpenReady}
          title={readyCount > 0 ? `Open the Ready tab to review ${readyCount} promotable items` : "No ready items to promote"}
          type="button"
        >
          <span aria-hidden="true" className="capture-inbox-hero-promote-split__icon">
            <WorkItemActionIcon className="capture-inbox-hero-promote-split__glyph" kind="approve" />
          </span>
          <span className="capture-inbox-hero-promote-split__label">
            {readyCount > 0 ? `Go to Ready (${readyCount})` : "No ready items"}
          </span>
        </button>
      </div>
    );
  }

  return (
    <div className={`capture-inbox-hero-promote-split${menuDisabled ? " is-menu-disabled" : ""}`}>
      <button
        className="capture-inbox-hero-promote-split__main"
        disabled={mainDisabled}
        onClick={onPromoteAllReady}
        title="Promote all ready items in this session"
        type="button"
      >
        <span aria-hidden="true" className="capture-inbox-hero-promote-split__icon">
          <WorkItemActionIcon className="capture-inbox-hero-promote-split__glyph" kind="promote" />
        </span>
        <span className="capture-inbox-hero-promote-split__label">{promoting ? "Promoting..." : "Promote ready"}</span>
      </button>
      <details
        className="capture-inbox-hero-promote-split__menu"
        onToggle={(event) => {
          if (menuDisabled) {
            event.currentTarget.removeAttribute("open");
          }
        }}
        ref={menuRef}
      >
        <summary aria-label="More promote options" className="capture-inbox-hero-promote-split__toggle">
          <MenuCaretIcon />
        </summary>
        <div className="capture-inbox-hero-promote-split__panel" role="menu">
          <p className="capture-inbox-hero-promote-split__panel-heading">Promote visible</p>
          {CAPTURE_INBOX_PROMOTE_TOP_BATCHES.map((limit) => (
            <button
              className="capture-inbox-hero-promote-split__panel-btn"
              disabled={topDisabled}
              key={limit}
              onClick={() => {
                closeMenu();
                onPromoteTop(limit);
              }}
              role="menuitem"
              title={`Promote top ${limit} from the current filtered view`}
              type="button"
            >
              Top {limit}
            </button>
          ))}
        </div>
      </details>
    </div>
  );
}
