import type { CapturedItem, CaptureInboxAction } from "../../types/capture-inbox";
import { captureInboxDetailsActionModel } from "../../lib/captureInboxUx";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

type CaptureInboxTileActionsProps = {
  item: CapturedItem;
  mutating: boolean;
  onAction: (item: CapturedItem, action: CaptureInboxAction) => void;
  pendingAction?: CaptureInboxAction | null;
  /** @deprecated Prefer captureInboxDetailsActionModel — kept for call-site compatibility. */
  promotable?: boolean;
  workingAction?: CaptureInboxAction | "delete_session" | "refresh" | null;
  variant?: "tile" | "inspector";
};

export function CaptureInboxTileActions({
  item,
  mutating,
  onAction,
  pendingAction = null,
  variant = "tile"
}: CaptureInboxTileActionsProps) {
  const disabled = mutating;
  const model = captureInboxDetailsActionModel(item);
  const barClass = [
    "review-board-tile-action-bar",
    "review-board-tile-action-grid",
    variant === "inspector" ? "is-inspector" : "is-tile",
    "capture-inbox-tile-action-bar"
  ].join(" ");

  if (model.kind === "promoted") {
    return (
      <div aria-label="Item actions" className={barClass}>
        <a
          aria-disabled={!model.reviewBoardHref ? true : undefined}
          className="review-board-tile-btn is-primary is-promoted-open"
          href={model.reviewBoardHref}
          onClick={!model.reviewBoardHref ? (event) => event.preventDefault() : undefined}
          tabIndex={!model.reviewBoardHref ? -1 : undefined}
          title="Open promoted candidate on Review Board"
        >
          <WorkItemActionIcon kind="open" />
          Open candidate
        </a>
      </div>
    );
  }

  if (!model.showPromote && !model.showRecheck && !model.showDelete) {
    return null;
  }

  const recoverPrimary = !model.showPromote && model.showRecheck;

  return (
    <div aria-label="Item actions" className={barClass}>
      {model.showPromote ? (
        <div className="review-board-tile-action-primary">
          <AsyncButton
            className="review-board-tile-btn is-primary"
            disabled={disabled}
            leadingIcon={<WorkItemActionIcon kind="promote" />}
            onClick={() => onAction(item, "promote_now")}
            pending={pendingAction === "promote_now"}
            pendingLabel="Promoting…"
            title="Promote to review"
            type="button"
          >
            Promote
          </AsyncButton>
        </div>
      ) : null}

      {recoverPrimary ? (
        <div className="review-board-tile-action-primary">
          <AsyncButton
            className="review-board-tile-btn is-primary is-recover is-no-arrow"
            disabled={disabled}
            leadingIcon={<WorkItemActionIcon kind="recheck" />}
            onClick={() => onAction(item, "re_evaluate_intake")}
            pending={pendingAction === "re_evaluate_intake"}
            pendingLabel="Re-checking…"
            type="button"
          >
            Re-check
          </AsyncButton>
        </div>
      ) : null}

      {model.showRecheck || model.showDelete ? (
        <div className={`review-board-tile-action-row ${model.showRecheck && model.showDelete && !recoverPrimary ? "is-split" : "is-secondary"}`}>
          {model.showRecheck && !recoverPrimary ? (
            <AsyncButton
              className="review-board-tile-btn is-muted"
              disabled={disabled}
              leadingIcon={<WorkItemActionIcon kind="recheck" />}
              onClick={() => onAction(item, "re_evaluate_intake")}
              pending={pendingAction === "re_evaluate_intake"}
              pendingLabel="Re-checking…"
              type="button"
            >
              Re-check
            </AsyncButton>
          ) : null}
          {model.showDelete ? (
            <AsyncButton
              className="review-board-tile-btn is-danger"
              disabled={disabled}
              leadingIcon={<WorkItemActionIcon kind="delete" />}
              onClick={() => onAction(item, "delete_items")}
              pending={pendingAction === "delete_items"}
              pendingLabel="Deleting…"
              type="button"
            >
              Delete
            </AsyncButton>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
