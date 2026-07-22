import type { Candidate } from "../../types/review-board";
import { reviewBoardDetailsActionVisibility } from "../../lib/reviewBoardQueueState";
import { AsyncButton } from "../shared/AsyncButton";
import { WorkItemActionIcon } from "../shared/WorkItemActionIcon";

type ReviewBoardTileActionsProps = {
  approvedForQueue?: boolean;
  candidate?: Pick<Candidate, "status" | "decision_status" | "in_reup_queue" | "reup_queue_status">;
  inReupQueue?: boolean;
  mutating: boolean;
  onApprove?: () => void;
  onApproveAndSend?: () => void;
  onLater: () => void;
  pendingAction?: string | null;
  onReject: () => void;
  onSendToQueue?: () => void;
  variant?: "tile" | "inspector";
};

export function ReviewBoardTileActions({
  approvedForQueue: approvedForQueueProp,
  candidate,
  inReupQueue: inReupQueueProp,
  mutating,
  onApprove,
  onApproveAndSend,
  onLater,
  pendingAction = null,
  onReject,
  onSendToQueue,
  variant = "tile"
}: ReviewBoardTileActionsProps) {
  const visibility = candidate
    ? reviewBoardDetailsActionVisibility(candidate)
    : {
        approvedForQueue: Boolean(approvedForQueueProp),
        inReupQueue: Boolean(inReupQueueProp),
        showApproveOnly: !approvedForQueueProp,
        showLater: true,
        showReject: true
      };
  const { approvedForQueue, inReupQueue, showApproveOnly, showLater, showReject } = visibility;
  const disabled = mutating;
  const barClass = [
    "review-board-tile-action-bar",
    "review-board-tile-action-grid",
    variant === "inspector" ? "is-inspector" : "is-tile",
    inReupQueue ? "is-queue-pair review-board-queue-pair is-promoted-pair" : ""
  ]
    .filter(Boolean)
    .join(" ");

  if (inReupQueue) {
    return (
      <div className={barClass} aria-label="Candidate actions">
        <a
          className={`review-board-tile-btn is-primary is-promoted-open${variant === "inspector" ? " review-board-inspector-queue-btn" : ""}`}
          href="/selection/reup-queue"
          title="Open this clip in Reup Queue"
        >
          <WorkItemActionIcon kind="open" />
          {variant === "inspector" ? "Open in Reup Queue" : "Open queue"}
        </a>
      </div>
    );
  }

  const showCompanionSplit = showLater || showReject;

  return (
    <div className={barClass} aria-label="Candidate actions">
      <div className="review-board-tile-action-primary">
        {approvedForQueue ? (
          <AsyncButton
            className="review-board-tile-btn is-primary"
            disabled={disabled}
            leadingIcon={<WorkItemActionIcon kind="send" />}
            onClick={onSendToQueue}
            pending={pendingAction === "send"}
            pendingLabel="Sending…"
            type="button"
          >
            Send to queue
          </AsyncButton>
        ) : (
          <AsyncButton
            className="review-board-tile-btn is-primary"
            disabled={disabled}
            leadingIcon={<WorkItemActionIcon kind="send" />}
            onClick={onApproveAndSend}
            pending={pendingAction === "approve-and-send"}
            pendingLabel="Sending…"
            type="button"
          >
            Approve & send
          </AsyncButton>
        )}
      </div>

      {showApproveOnly && onApprove ? (
        <div className="review-board-tile-action-row is-secondary">
          <AsyncButton
            className="review-board-tile-btn is-secondary"
            disabled={disabled}
            leadingIcon={<WorkItemActionIcon kind="approve" />}
            onClick={onApprove}
            pending={pendingAction === "approved"}
            pendingLabel="Approving…"
            type="button"
          >
            Approve only
          </AsyncButton>
        </div>
      ) : null}

      {showCompanionSplit ? (
        <div className={`review-board-tile-action-row ${showLater && showReject ? "is-split" : "is-secondary"}`}>
          {showLater ? (
            <AsyncButton
              className="review-board-tile-btn is-muted"
              disabled={disabled}
              leadingIcon={<WorkItemActionIcon kind="later" />}
              onClick={onLater}
              pending={pendingAction === "in_review"}
              pendingLabel="Updating…"
              type="button"
            >
              Later
            </AsyncButton>
          ) : null}
          {showReject ? (
            <AsyncButton
              className="review-board-tile-btn is-danger"
              disabled={disabled}
              leadingIcon={<WorkItemActionIcon kind="reject" />}
              onClick={onReject}
              pending={pendingAction === "rejected"}
              pendingLabel="Rejecting…"
              type="button"
            >
              Reject
            </AsyncButton>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
