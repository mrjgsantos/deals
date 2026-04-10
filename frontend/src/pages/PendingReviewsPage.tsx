import { useEffect, useMemo, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { ReviewItem } from "../types";
import { DealSummary } from "../components/DealSummary";
import { StatusMessage } from "../components/StatusMessage";
import { formatDateTime, formatMoney, formatPercent, toSentenceCase, toTimestamp } from "../lib/format";
import { Badge } from "../components/Badge";
import {
  getHistoryStrengthTone,
  getHistorySupportSummary,
  getPublicationReadiness,
  getQualityScore,
  getSavingsPercentValue,
  hasFakeDiscountRisk,
  hasWeakHistory,
  getSourceLabel,
  getSourceLinkType,
  getSourceSearchText,
  isLowConfidenceDeal,
} from "../lib/dealSignals";

type ActionState = {
  reviewId: string;
  action: "approve" | "reject";
} | null;

type ReviewSort = "priority" | "score" | "savings" | "newest";
type ReviewFocus = "all" | "high_score" | "needs_attention" | "weak_history" | "fake_discount";

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong while talking to the API.", {
    404: "The review item no longer exists.",
    409: "This review was already resolved or the deal is no longer in a valid pending state.",
  });
}

function matchesReviewFocus(item: ReviewItem, focus: ReviewFocus): boolean {
  if (focus === "all") {
    return true;
  }
  if (focus === "high_score") {
    return getQualityScore(item.deal) >= 65;
  }
  if (focus === "weak_history") {
    return hasWeakHistory(item.deal);
  }
  if (focus === "fake_discount") {
    return hasFakeDiscountRisk(item.deal);
  }
  return (
    isLowConfidenceDeal(item.deal) ||
    hasWeakHistory(item.deal) ||
    hasFakeDiscountRisk(item.deal) ||
    getQualityScore(item.deal) < 65
  );
}

function getDecisionFeedbackMessage(action: "approve" | "reject", dealStatus: string): string {
  const formattedStatus = toSentenceCase(dealStatus);
  if (action === "approve") {
    return `Review approved. Deal is now ${formattedStatus}.`;
  }
  return `Review rejected. Deal is now ${formattedStatus}.`;
}

export function PendingReviewsPage() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [selectedReviewId, setSelectedReviewId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [actionState, setActionState] = useState<ActionState>(null);
  const [sortBy, setSortBy] = useState<ReviewSort>("priority");
  const [focus, setFocus] = useState<ReviewFocus>("all");
  const [filterText, setFilterText] = useState("");

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

  const queueSummary = useMemo(
    () => ({
      highScore: items.filter((item) => getQualityScore(item.deal) >= 65).length,
      needsAttention: items.filter((item) => matchesReviewFocus(item, "needs_attention")).length,
      fakeDiscount: items.filter((item) => hasFakeDiscountRisk(item.deal)).length,
      weakHistory: items.filter((item) => hasWeakHistory(item.deal)).length,
    }),
    [items],
  );

  const visibleItems = useMemo(() => {
    const normalizedFilter = filterText.trim().toLowerCase();
    const filtered = items.filter((item) => {
      if (!matchesReviewFocus(item, focus)) {
        return false;
      }
      if (normalizedFilter.length === 0) {
        return true;
      }
      return getSourceSearchText(item.deal).includes(normalizedFilter);
    });

    return [...filtered].sort((left, right) => {
      if (sortBy === "score") {
        return getQualityScore(right.deal) - getQualityScore(left.deal);
      }
      if (sortBy === "savings") {
        return getSavingsPercentValue(right.deal) - getSavingsPercentValue(left.deal);
      }
      if (sortBy === "newest") {
        return (toTimestamp(right.created_at) ?? 0) - (toTimestamp(left.created_at) ?? 0);
      }

      return left.priority - right.priority || (toTimestamp(left.created_at) ?? 0) - (toTimestamp(right.created_at) ?? 0);
    });
  }, [filterText, focus, items, sortBy]);

  const selectedItem = useMemo(
    () => visibleItems.find((item) => item.id === selectedReviewId) ?? visibleItems[0] ?? null,
    [selectedReviewId, visibleItems],
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
      const decision = action === "approve" ? await api.approveReview(reviewId) : await api.rejectReview(reviewId);

      const nextItems = items.filter((item) => item.id !== reviewId);
      setItems(nextItems);
      setSelectedReviewId(nextItems[0]?.id ?? null);
      setFeedback({
        tone: "success",
        message: getDecisionFeedbackMessage(action, decision.deal_status),
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
        <div className="header-meta header-meta-stack">
          <div className="counter-row"><span className="counter">{items.length} pending</span>{visibleItems.length !== items.length ? <span className="counter">{visibleItems.length} shown</span> : null}</div>
          <div className="filter-row">
            <label className="filter-control">
              <span>Sort</span>
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value as ReviewSort)}>
                <option value="priority">Priority</option>
                <option value="score">Score</option>
                <option value="savings">Savings %</option>
                <option value="newest">Newest</option>
              </select>
            </label>
            <label className="filter-control">
              <span>Focus</span>
              <select value={focus} onChange={(event) => setFocus(event.target.value as ReviewFocus)}>
                <option value="all">All reviews</option>
                <option value="high_score">Score 65+</option>
                <option value="needs_attention">Needs attention</option>
                <option value="weak_history">Weak history</option>
                <option value="fake_discount">Fake discount risk</option>
              </select>
            </label>
            <label className="filter-control filter-control-wide">
              <span>Filter</span>
              <input
                type="text"
                value={filterText}
                onChange={(event) => setFilterText(event.target.value)}
                placeholder="Title, source, merchant"
              />
            </label>
            <button className="secondary-button" onClick={() => void loadPendingReviews()}>
              Refresh
            </button>
          </div>
        </div>
      </div>

      <div className="summary-card-grid">
        <div className="summary-card">
          <span className="summary-card-kicker">Score 65+</span>
          <strong className="summary-card-value">{queueSummary.highScore}</strong>
          <span className="summary-card-note">Higher-scoring deals to sanity check first.</span>
        </div>
        <div className="summary-card">
          <span className="summary-card-kicker">Needs attention</span>
          <strong className="summary-card-value">{queueSummary.needsAttention}</strong>
          <span className="summary-card-note">Low confidence, weak history, or fake-discount risk.</span>
        </div>
        <div className="summary-card">
          <span className="summary-card-kicker">Fake discount risk</span>
          <strong className="summary-card-value">{queueSummary.fakeDiscount}</strong>
          <span className="summary-card-note">Check baseline and recent history before approving.</span>
        </div>
        <div className="summary-card">
          <span className="summary-card-kicker">Weak history</span>
          <strong className="summary-card-value">{queueSummary.weakHistory}</strong>
          <span className="summary-card-note">Savings may be unsupported by enough observations.</span>
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
            {visibleItems.map((item) => {
              const isBusy = actionState?.reviewId === item.id;
              const isSelected = item.id === selectedItem?.id;
              const sourceLabel = getSourceLabel(item.deal.deal_url);
              const sourceLinkType = getSourceLinkType(item.deal.deal_url);
              const lowConfidence = isLowConfidenceDeal(item.deal);
              const publicationState = getPublicationReadiness(item.deal);
              const historySupport = getHistorySupportSummary(item.deal);
              const historyTone = getHistoryStrengthTone(item.deal);

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
                  <div className="review-list-signal-row">
                    <span className="price-strong">{formatMoney(item.deal.current_price, item.deal.currency)}</span>
                    <span className="muted">vs {formatMoney(item.deal.previous_price, item.deal.currency)}</span>
                    <span className="score-chip">Q{item.deal.score_breakdown.quality_score ?? "—"}</span>
                    <span className="score-chip">{formatPercent(item.deal.savings_percent)}</span>
                  </div>
                  <div className="review-list-signal-row review-list-signal-row-secondary">
                    <span className="muted">Save {formatMoney(item.deal.savings_amount, item.deal.currency)}</span>
                    <Badge value={historySupport} tone={historyTone} />
                  </div>
                  <div className="badge-cluster badge-cluster-wrap">
                    <Badge value={publicationState.label} tone={publicationState.tone} />
                    {lowConfidence ? <Badge value="possible low confidence" tone="warning" /> : null}
                    {item.deal.score_breakdown.fake_discount ? <Badge value="fake discount risk" tone="danger" /> : null}
                    {sourceLinkType === "google_redirect" ? <Badge value="google redirect" tone="warning" /> : null}
                  </div>
                  <div className="review-list-meta">
                    <span>{formatDateTime(item.created_at)}</span>
                    <span>{sourceLabel ?? item.reason}</span>
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
                  <span>Quality {selectedItem.deal.score_breakdown.quality_score ?? "—"}</span>
                  <span>{formatPercent(selectedItem.deal.savings_percent)} off</span>
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
