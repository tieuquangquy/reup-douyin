import type { CapturedItem, CaptureInboxAction } from "../../types/capture-inbox";

type CaptureInboxTileActionsProps = {
  item: CapturedItem;
  mutating: boolean;
  onAction: (item: CapturedItem, action: CaptureInboxAction) => void;
  onFocusItem: (itemId: string) => void;
  promotable: boolean;
  workingAction: CaptureInboxAction | "delete_session" | "refresh" | null;
};

function actionLabel(base: string, apiAction: CaptureInboxAction, workingAction: CaptureInboxTileActionsProps["workingAction"]): string {
  return workingAction === apiAction ? "Working..." : base;
}

export function CaptureInboxTileActions({
  item,
  mutating,
  onAction,
  onFocusItem,
  promotable,
  workingAction
}: CaptureInboxTileActionsProps) {
  const disabled = mutating;
  const promoted = item.status === "PROMOTED";
  const reviewBoardHref = item.promoted_video_candidate_id
    ? `/selection/review-board?candidate=${encodeURIComponent(item.promoted_video_candidate_id)}`
    : undefined;

  if (promoted) {
    return (
      <div
        aria-label="Item actions"
        className="review-board-tile-action-bar review-board-tile-action-grid is-tile is-promoted-pair capture-inbox-tile-action-bar"
      >
        <a
          aria-disabled={!reviewBoardHref ? true : undefined}
          className="review-board-tile-btn is-primary is-promoted-open"
          href={reviewBoardHref}
          onClick={!reviewBoardHref ? (event) => event.preventDefault() : undefined}
          tabIndex={!reviewBoardHref ? -1 : undefined}
          title="Open promoted candidate on Review Board"
        >
          Open candidate
        </a>
        <button
          className="review-board-tile-btn is-secondary is-promoted-details"
          disabled={disabled}
          onClick={() => onFocusItem(item.id)}
          title="Inspect item details"
          type="button"
        >
          Details
        </button>
      </div>
    );
  }

  const recheckDisabled = disabled;
  const deleteDisabled = disabled;

  return (
    <div
      aria-label="Item actions"
      className="review-board-tile-action-bar review-board-tile-action-grid is-tile capture-inbox-tile-action-bar"
    >
      <div className="review-board-tile-action-primary">
        <button
          className="review-board-tile-btn is-primary"
          disabled={disabled || !promotable}
          onClick={() => onAction(item, "promote_now")}
          title={promotable ? "Promote to review" : "Item is not ready to promote"}
          type="button"
        >
          {actionLabel("Promote", "promote_now", workingAction)}
        </button>
      </div>

      <div className="review-board-tile-action-row is-split">
        <button
          className="review-board-tile-btn is-muted"
          disabled={recheckDisabled}
          onClick={() => onAction(item, "re_evaluate_intake")}
          type="button"
        >
          {actionLabel("Re-check", "re_evaluate_intake", workingAction)}
        </button>
        <button
          className="review-board-tile-btn is-danger"
          disabled={deleteDisabled}
          onClick={() => onAction(item, "delete_items")}
          type="button"
        >
          {actionLabel("Delete", "delete_items", workingAction)}
        </button>
      </div>

      <div className="review-board-tile-action-row is-tertiary">
        <button
          className="review-board-tile-btn is-ghost"
          disabled={disabled}
          onClick={() => onFocusItem(item.id)}
          type="button"
        >
          View details
        </button>
      </div>
    </div>
  );
}
