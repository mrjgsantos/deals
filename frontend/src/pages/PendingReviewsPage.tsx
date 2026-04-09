import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { ReviewItem } from "../types";
import { DealSummary } from "../components/DealSummary";
import { StatusMessage } from "../components/StatusMessage";
import { formatDateTime } from "../lib/format";
import { Badge } from "../components/Badge";

type ActionState = {
  reviewId: string;
  action: "approve" | "reject";
} | null;

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 409) {
      return "This review was already resolved or the deal is no longer in a valid pending state.";
    }
    if (error.status === 404) {
      return "The review item no longer exists.";
    }
    return `Request failed: ${error.message}`;
  }

  return "Something went wrong while talking to the API.";
}

export function PendingReviewsPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [actionState, setActionState] = useState<ActionState>(null);

  async function loadPendingReviews() {
    setIsLoading(true);
    setError(null);

    try {
      const data = await api.getPendingReviews();
      setItems(data);
      setSelectedReviewId((current) => current ?? data[0]?.id ?? null);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadPendingReviews();
  }, []);

  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedReviewId) ?? items[0] ?? null,
    [items, selectedReviewId],
  );

  useEffect(() => {
    if (selectedItem && selectedItem.id !== selectedReviewId) {
      setSelectedReviewId(selectedItem.id);
    }
  }, [selectedItem, selectedReviewId]);

  async function handleDecision(reviewId: string, action: "approve" | "reject") {
    setActionState({ reviewId, action });
    setFeedback(null);

    try {
      if (action === "approve") {
        await api.approveReview(reviewId);
      } else {
        await api.rejectReview(reviewId);
      }

      const nextItems = items.filter((item) => item.id !== reviewId);
      setItems(nextItems);
      setSelectedReviewId(nextItems[0]?.id ?? null);
      setFeedback({
        tone: "success",
        message: action === "approve" ? "Review approved." : "Review rejected.",
      });
    } catch (actionError) {
      setFeedback({
        tone: "error",
        message: getErrorMessage(actionError),
      });
      await loadPendingReviews();
    } finally {
      setActionState(null);
    }
  }

  if (isLoading) {
    return <StatusMessage tone="info" title="Loading pending reviews" detail="Fetching the review queue from the API." />;
  }

  if (error) {
    return <StatusMessage tone="error" title="Could not load pending reviews" detail={error} />;
  }

  return (
    <div className="screen-layout">
      <div className="screen-header">
        <div>
          <div className="eyebrow">Review queue</div>
          <h1>Pending Reviews</h1>
          <p className="screen-subtitle">Approve or reject generated deals with full scoring context.</p>
        </div>
        <div className="header-meta">
          <span className="counter">{items.length} pending</span>
          <button className="secondary-button" onClick={() => void loadPendingReviews()}>
            Refresh
          </button>
        </div>
      </div>

      {feedback ? <StatusMessage tone={feedback.tone} title={feedback.message} /> : null}

      {items.length === 0 ? (
        <div className="empty-state-shell">
          <StatusMessage tone="info" title="No pending reviews" detail="The queue is currently clear." />
        </div>
      ) : (
        <div className="review-layout">
          <aside className="review-list">
            {items.map((item) => {
              const isBusy = actionState?.reviewId === item.id;
              const isSelected = item.id === selectedItem?.id;

              return (
                <button
                  key={item.id}
                  type="button"
                  className={isSelected ? "review-list-item review-list-item-active" : "review-list-item"}
                  onClick={() => setSelectedReviewId(item.id)}
                  disabled={Boolean(actionState)}
                >
                  <div className="review-list-top">
                    <Badge value={item.status} />
                    <span className="review-priority">P{item.priority}</span>
                  </div>
                  <div className="review-list-title">{item.deal.title}</div>
                  <div className="review-list-meta">
                    <span>{formatDateTime(item.created_at)}</span>
                    <span>{item.reason}</span>
                  </div>
                  <div className="review-list-actions">
                    <span className="price-strong">{item.deal.currency} {item.deal.current_price}</span>
                    {isBusy ? <span className="muted">Updating…</span> : null}
                  </div>
                </button>
              );
            })}
          </aside>

          {selectedItem ? (
            <section className="review-detail">
              <div className="review-detail-toolbar">
                <div className="toolbar-meta">
                  <Badge value={selectedItem.status} />
                  <span>Created {formatDateTime(selectedItem.created_at)}</span>
                </div>
                <div className="toolbar-actions">
                  <button
                    className="secondary-button danger-button"
                    onClick={() => void handleDecision(selectedItem.id, "reject")}
                    disabled={Boolean(actionState)}
                  >
                    {actionState?.reviewId === selectedItem.id && actionState.action === "reject" ? "Rejecting…" : "Reject"}
                  </button>
                  <button
                    className="primary-button"
                    onClick={() => void handleDecision(selectedItem.id, "approve")}
                    disabled={Boolean(actionState)}
                  >
                    {actionState?.reviewId === selectedItem.id && actionState.action === "approve" ? "Approving…" : "Approve"}
                  </button>
                </div>
              </div>

              <DealSummary deal={selectedItem.deal} />
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
