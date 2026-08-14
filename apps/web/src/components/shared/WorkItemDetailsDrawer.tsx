/**
 * Work item details overlay — right drawer matching Ops Users edit drawer.
 * Renders nothing when closed so Capture / Review / Reup stay full-width.
 */
import { useEffect, type ReactNode } from "react";

type Props = {
  open: boolean;
  onClose: () => void;
  titleId: string;
  eyebrow: string;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
  /** Optional controls under the title (legacy peer mode switch). */
  headerExtra?: ReactNode;
  /** Optional leading control before the title (e.g. back to Overview). */
  headerLeading?: ReactNode;
};

export function WorkItemDetailsDrawer({
  open,
  onClose,
  titleId,
  eyebrow,
  title,
  children,
  footer,
  headerExtra,
  headerLeading,
}: Props) {
  useEffect(() => {
    if (!open) return;
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="work-item-details-drawer-backdrop" onClick={onClose} role="presentation">
      <aside
        aria-labelledby={titleId}
        aria-modal="true"
        className="work-item-details-drawer"
        role="dialog"
        onClick={(event) => event.stopPropagation()}
      >
        <header className="work-item-details-drawer-header">
          {headerLeading ? <div className="work-item-details-drawer-header__leading">{headerLeading}</div> : null}
          <div className="work-item-details-drawer-identity">
            <p className="work-item-details-drawer-eyebrow">{eyebrow}</p>
            <h2 id={titleId}>{title}</h2>
            {headerExtra ? <div className="work-item-details-drawer-header__extra">{headerExtra}</div> : null}
          </div>
          <button
            aria-label="Close details"
            className="work-item-details-drawer-close"
            type="button"
            onClick={onClose}
          >
            ×
          </button>
        </header>
        <div className="work-item-details-drawer__body">{children}</div>
        {footer ? <div className="work-item-details-drawer__footer">{footer}</div> : null}
      </aside>
    </div>
  );
}
