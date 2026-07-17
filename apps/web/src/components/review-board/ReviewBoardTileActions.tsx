type ReviewBoardTileActionsProps = {
  approvedForQueue: boolean;
  inReupQueue: boolean;
  mutating: boolean;
  onApprove?: () => void;
  onApproveAndSend?: () => void;
  onDetails: () => void;
  onLater: () => void;
  onReject: () => void;
  onSendToQueue?: () => void;
  variant?: "tile" | "inspector";
};

export function ReviewBoardTileActions({
  approvedForQueue,
  inReupQueue,
  mutating,
  onApprove,
  onApproveAndSend,
  onDetails,
  onLater,
  onReject,
  onSendToQueue,
  variant = "tile"
}: ReviewBoardTileActionsProps) {
  const disabled = mutating;
  const barClass = [
    "review-board-tile-action-bar",
    "review-board-tile-action-grid",
    variant === "inspector" ? "is-inspector" : "is-tile",
    inReupQueue ? "is-queue-pair review-board-queue-pair is-promoted-pair" : ""
  ]
    .filter(Boolean)
    .join(" ");

  if (variant === "inspector" && !inReupQueue) {
    return (
      <div className={barClass} aria-label="Candidate actions">
        <div className="review-board-tile-action-primary">
          {approvedForQueue ? (
            <button className="review-board-tile-btn is-primary" disabled={disabled} onClick={onSendToQueue} type="button">
              Send to queue
            </button>
          ) : (
            <button className="review-board-tile-btn is-primary" disabled={disabled} onClick={onApprove} type="button">
              Approve
            </button>
          )}
        </div>
        <div className="review-board-tile-action-row is-split">
          <button className="review-board-tile-btn is-muted" disabled={disabled} onClick={onLater} type="button">
            Later
          </button>
          <button className="review-board-tile-btn is-danger" disabled={disabled} onClick={onReject} type="button">
            Reject
          </button>
        </div>
      </div>
    );
  }

  if (inReupQueue) {
    if (variant === "inspector") {
      return (
        <div className={barClass} aria-label="Candidate actions">
          <a
            className="review-board-tile-btn is-primary is-promoted-open review-board-inspector-queue-btn"
            href="/selection/reup-queue"
            title="Open this clip in Reup Queue"
          >
            Open in Reup Queue
          </a>
        </div>
      );
    }

    return (
      <div className={barClass} aria-label="Candidate actions">
        <a
          className="review-board-tile-btn is-primary is-promoted-open"
          href="/selection/reup-queue"
          title="Open this clip in Reup Queue"
        >
          {variant === "inspector" ? "Open in Reup Queue" : "Open queue"}
        </a>
        <button
          className="review-board-tile-btn is-secondary is-promoted-details"
          disabled={disabled}
          onClick={onDetails}
          title="Inspect candidate details"
          type="button"
        >
          Details
        </button>
      </div>
    );
  }

  return (
    <div className={barClass} aria-label="Candidate actions">
      <div className="review-board-tile-action-primary">
        {approvedForQueue ? (
          <button className="review-board-tile-btn is-primary" disabled={disabled} onClick={onSendToQueue} type="button">
            Send to queue
          </button>
        ) : (
          <button className="review-board-tile-btn is-primary" disabled={disabled} onClick={onApproveAndSend} type="button">
            Approve & send
          </button>
        )}
      </div>

      {!approvedForQueue && onApprove ? (
        <div className="review-board-tile-action-row is-secondary">
          <button className="review-board-tile-btn is-secondary" disabled={disabled} onClick={onApprove} type="button">
            Approve only
          </button>
        </div>
      ) : null}

      <div className="review-board-tile-action-row is-split">
        <button className="review-board-tile-btn is-muted" disabled={disabled} onClick={onLater} type="button">
          Later
        </button>
        <button className="review-board-tile-btn is-danger" disabled={disabled} onClick={onReject} type="button">
          Reject
        </button>
      </div>

      <div className="review-board-tile-action-row is-tertiary">
        <button className="review-board-tile-btn is-ghost" disabled={disabled} onClick={onDetails} type="button">
          View details
        </button>
      </div>
    </div>
  );
}