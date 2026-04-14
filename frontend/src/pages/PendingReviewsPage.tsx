import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { Deal, ReviewQueueItem, ReviewQueuePage } from "../types";
import { DealSummary } from "../components/DealSummary";
import { PriceBar } from "../components/PriceBar";
import { formatMoney, formatPercent, formatRelativeTime, normalizePercentValue } from "../lib/format";
import { getSourceLabel, getSourceLinkType } from "../lib/dealSignals";

// ─── Types ────────────────────────────────────────────────────────────────────

type ActionState = { reviewId: string; action: "approve" | "reject" } | null;
type SortBy = "priority" | "score" | "savings" | "newest";
type Focus = "all" | "high_score" | "needs_attention" | "fake_discount";

function getSavingsPercent(item: ReviewQueueItem): number {
  return normalizePercentValue(item.savings_percent) ?? 0;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong.", {
    404: "The review item no longer exists.",
    409: "This review was already resolved or the deal is in an invalid state.",
  });
}

function sourceLabel(item: ReviewQueueItem): string {
  if (item.asin) return "Amazon";
  const label = getSourceLabel(item.deal_url);
  return label ?? item.source_category ?? "Unknown";
}

function isAmazon(item: ReviewQueueItem): boolean {
  return Boolean(item.asin);
}

function itemMatchesFocus(item: ReviewQueueItem, focus: Focus): boolean {
  if (focus === "all") return true;
  if (focus === "high_score") return (item.quality_score ?? 0) >= 65;
  if (focus === "fake_discount") return item.fake_discount;
  // needs_attention
  return (
    item.fake_discount ||
    item.confidence_level === "low" ||
    (item.quality_score !== null && item.quality_score < 50) ||
    item.quality_reasons.some((r) =>
      ["limited_price_history", "weak_discount_support", "limited_discount_support"].includes(r),
    )
  );
}

// ─── Queue Card ───────────────────────────────────────────────────────────────

function QueueCard({
  item,
  isBusy,
  onApprove,
  onReject,
  onDetail,
}: {
  item: ReviewQueueItem;
  isBusy: boolean;
  onApprove: () => void;
  onReject: () => void;
  onDetail: () => void;
}) {
  const src = sourceLabel(item);
  const amazon = isAmazon(item);
  const linkType = getSourceLinkType(item.deal_url);
  const score = item.quality_score;
  const hasDiscount = item.savings_percent !== null && parseFloat(item.savings_percent ?? "0") > 0;
  const highScore = score !== null && score >= 70;
  const lowScore = score !== null && score < 50;

  return (
    <article className={`qcard${isBusy ? " qcard-busy" : ""}`}>
      {/* ── Header ── */}
      <div className="qcard-header">
        <div className="qcard-thumb">
          {item.image_url ? (
            <img src={item.image_url} alt="" loading="lazy" />
          ) : (
            <div className="qcard-thumb-placeholder" />
          )}
        </div>
        <div className="qcard-header-body">
          <div className="qcard-meta-row">
            <span className={`qcard-source-badge${amazon ? " qcard-source-amazon" : " qcard-source-google"}`}>
              {amazon ? "Amazon" : src}
            </span>
            {score !== null && (
              <span className={`qcard-score${highScore ? " qcard-score-high" : lowScore ? " qcard-score-low" : ""}`}>
                Q{score}
              </span>
            )}
            {item.promotable && <span className="qcard-promotable">✓ promotable</span>}
          </div>
          <h3 className="qcard-title">{item.title}</h3>
        </div>
      </div>

      {/* ── Pricing ── */}
      <div className="qcard-price-row">
        <span className="qcard-price-current">{formatMoney(item.current_price, item.currency)}</span>
        {item.previous_price && (
          <span className="qcard-price-was">was {formatMoney(item.previous_price, item.currency)}</span>
        )}
        {hasDiscount && (
          <span className="qcard-discount-pill">{formatPercent(item.savings_percent)} off</span>
        )}
      </div>

      {/* ── Price History Bar ── */}
      <PriceBar priceHistory={item.price_history} currentPrice={item.current_price} currency={item.currency} />

      {/* ── Flags ── */}
      <div className="qcard-flags">
        {item.fake_discount && <span className="qcard-flag qcard-flag-danger">fake discount risk</span>}
        {item.confidence_level === "low" && <span className="qcard-flag qcard-flag-warn">low confidence</span>}
        {item.confidence_level === "medium" && <span className="qcard-flag qcard-flag-warn">medium confidence</span>}
        {linkType === "google_redirect" && <span className="qcard-flag qcard-flag-warn">google redirect</span>}
        {item.price_history && item.price_history.observation_count_all_time < 4 && (
          <span className="qcard-flag qcard-flag-warn">sparse history ({item.price_history.observation_count_all_time} obs)</span>
        )}
      </div>

      {/* ── Footer ── */}
      <div className="qcard-footer">
        <span className="qcard-age">{formatRelativeTime(item.created_at)}</span>
        <div className="qcard-actions">
          <button
            className="qcard-btn-reject"
            onClick={onReject}
            disabled={isBusy}
            title="Reject this deal"
          >
            {isBusy ? "…" : "Reject"}
          </button>
          <button
            className="qcard-btn-detail"
            onClick={onDetail}
            disabled={isBusy}
            title="Open full deal detail"
          >
            Detail
          </button>
          <button
            className="qcard-btn-approve"
            onClick={onApprove}
            disabled={isBusy}
            title="Approve this deal"
          >
            {isBusy ? "…" : "Approve"}
          </button>
        </div>
      </div>
    </article>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function QueueSkeleton() {
  return (
    <div className="qgrid">
      {Array.from({ length: 6 }).map((_, i) => (
        <div key={i} className="qcard qcard-skeleton">
          <div className="qcard-header">
            <div className="qcard-thumb"><div className="qcard-thumb-placeholder" /></div>
            <div className="qcard-header-body">
              <div className="skeleton-block skeleton-badge" style={{ width: 80, height: 20, borderRadius: 999 }} />
              <div className="skeleton-block skeleton-title" style={{ marginTop: 8 }} />
              <div className="skeleton-block skeleton-title skeleton-title-short" style={{ marginTop: 6 }} />
            </div>
          </div>
          <div className="skeleton-block skeleton-price" style={{ marginTop: 14 }} />
          <div className="skeleton-block" style={{ height: 24, borderRadius: 6, marginTop: 10 }} />
          <div className="skeleton-block skeleton-button" style={{ marginTop: 14, width: "100%", borderRadius: 8 }} />
        </div>
      ))}
    </div>
  );
}

// ─── Detail Drawer ────────────────────────────────────────────────────────────

function DetailDrawer({
  reviewId: _reviewId,
  deal,
  isLoading,
  isBusy,
  onClose,
  onApprove,
  onReject,
}: {
  reviewId: string;
  deal: Deal | null;
  isLoading: boolean;
  isBusy: boolean;
  onClose: () => void;
  onApprove: () => void;
  onReject: () => void;
}) {
  const drawerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <>
      <div className="drawer-overlay" onClick={onClose} />
      <div className="drawer" ref={drawerRef}>
        <div className="drawer-toolbar">
          <button className="drawer-close" onClick={onClose} aria-label="Close">✕</button>
          <div className="drawer-actions">
            <button className="secondary-button danger-button" onClick={onReject} disabled={isBusy}>
              {isBusy ? "Rejecting…" : "Reject"}
            </button>
            <button className="primary-button" onClick={onApprove} disabled={isBusy}>
              {isBusy ? "Approving…" : "Approve"}
            </button>
          </div>
        </div>
        <div className="drawer-body">
          {isLoading && <div className="drawer-loading">Loading deal details…</div>}
          {!isLoading && deal && <DealSummary deal={deal} />}
        </div>
      </div>
    </>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

const LIMIT = 50;

export function PendingReviewsPage() {
  const [pages, setPages] = useState<ReviewQueuePage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ tone: "success" | "error"; message: string } | null>(null);
  const [actionState, setActionState] = useState<ActionState>(null);
  const [sortBy, setSortBy] = useState<SortBy>("priority");
  const [focus, setFocus] = useState<Focus>("all");
  const [filterText, setFilterText] = useState("");
  const [detailReviewId, setDetailReviewId] = useState<string | null>(null);
  const [detailDeal, setDetailDeal] = useState<Deal | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const allItems = useMemo(() => pages.flatMap((p) => p.items), [pages]);
  const offset = allItems.length;

  async function load(replace = false) {
    try {
      const page = await api.getReviewQueue(replace ? 0 : 0, LIMIT);
      setPages([page]);
      setHasMore(page.has_more);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function loadMore() {
    setIsLoadingMore(true);
    try {
      const page = await api.getReviewQueue(offset, LIMIT);
      setPages((prev) => [...prev, page]);
      setHasMore(page.has_more);
    } catch (err) {
      setFeedback({ tone: "error", message: getErrorMessage(err) });
    } finally {
      setIsLoadingMore(false);
    }
  }

  useEffect(() => {
    setIsLoading(true);
    load(true).finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleItems = useMemo(() => {
    const normalized = filterText.trim().toLowerCase();
    const filtered = allItems.filter((item) => {
      if (!itemMatchesFocus(item, focus)) return false;
      if (!normalized) return true;
      return (
        item.title.toLowerCase().includes(normalized) ||
        (item.source_category ?? "").toLowerCase().includes(normalized) ||
        (item.asin ?? "").toLowerCase().includes(normalized)
      );
    });

    return [...filtered].sort((a, b) => {
      if (sortBy === "score") return (b.quality_score ?? 0) - (a.quality_score ?? 0);
      if (sortBy === "savings") return getSavingsPercent(b) - getSavingsPercent(a);
      if (sortBy === "newest") return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      return a.priority - b.priority || new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
    });
  }, [allItems, focus, filterText, sortBy]);

  const queueSummary = useMemo(() => ({
    total: allItems.length,
    highScore: allItems.filter((i) => (i.quality_score ?? 0) >= 65).length,
    needsAttention: allItems.filter((i) => itemMatchesFocus(i, "needs_attention")).length,
    fakeDiscount: allItems.filter((i) => i.fake_discount).length,
    amazon: allItems.filter((i) => Boolean(i.asin)).length,
  }), [allItems]);

  async function handleDecision(reviewId: string, _dealId: string, action: "approve" | "reject") {
    setActionState({ reviewId, action });
    setFeedback(null);
    try {
      const decision = action === "approve" ? await api.approveReview(reviewId) : await api.rejectReview(reviewId);
      setPages((prev) => prev.map((p) => ({ ...p, items: p.items.filter((i) => i.id !== reviewId) })));
      if (detailReviewId === reviewId) setDetailReviewId(null);
      setFeedback({
        tone: "success",
        message: action === "approve"
          ? `Approved — deal is now ${decision.deal_status}.`
          : `Rejected — deal is now ${decision.deal_status}.`,
      });
    } catch (err) {
      setFeedback({ tone: "error", message: getErrorMessage(err) });
    } finally {
      setActionState(null);
    }
  }

  const openDetail = useCallback(async (reviewId: string, dealId: string) => {
    setDetailReviewId(reviewId);
    setDetailDeal(null);
    setIsLoadingDetail(true);
    try {
      const deal = await api.getDeal(dealId);
      setDetailDeal(deal);
    } catch {
      // Detail failed to load; drawer shows error state
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const closeDetail = useCallback(() => {
    setDetailReviewId(null);
    setDetailDeal(null);
  }, []);

  if (isLoading) {
    return (
      <div className="screen-layout">
        <div className="screen-header">
          <div>
            <div className="eyebrow">Review queue</div>
            <h1>Pending Reviews</h1>
          </div>
        </div>
        <QueueSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="screen-layout">
        <div className="screen-header">
          <div>
            <div className="eyebrow">Review queue</div>
            <h1>Pending Reviews</h1>
          </div>
        </div>
        <div className="qerror">{error}</div>
      </div>
    );
  }

  return (
    <div className="screen-layout">
      {/* ── Header ── */}
      <div className="screen-header">
        <div>
          <div className="eyebrow">Review queue</div>
          <h1>Pending Reviews</h1>
        </div>
        <div className="header-meta header-meta-stack">
          <div className="qstats-row">
            <span className="qstat">{queueSummary.total} pending</span>
            {queueSummary.amazon > 0 && <span className="qstat qstat-amazon">{queueSummary.amazon} Amazon</span>}
            {queueSummary.fakeDiscount > 0 && <span className="qstat qstat-danger">{queueSummary.fakeDiscount} fake discount risk</span>}
            {queueSummary.highScore > 0 && <span className="qstat qstat-success">{queueSummary.highScore} score 65+</span>}
          </div>
          <div className="filter-row">
            <label className="filter-control">
              <span>Sort</span>
              <select value={sortBy} onChange={(e) => setSortBy(e.target.value as SortBy)}>
                <option value="priority">Priority</option>
                <option value="score">Score</option>
                <option value="savings">Savings %</option>
                <option value="newest">Newest</option>
              </select>
            </label>
            <label className="filter-control">
              <span>Focus</span>
              <select value={focus} onChange={(e) => setFocus(e.target.value as Focus)}>
                <option value="all">All</option>
                <option value="high_score">Score 65+</option>
                <option value="needs_attention">Needs attention</option>
                <option value="fake_discount">Fake discount risk</option>
              </select>
            </label>
            <label className="filter-control filter-control-wide">
              <span>Filter</span>
              <input
                type="text"
                value={filterText}
                onChange={(e) => setFilterText(e.target.value)}
                placeholder="Title, category, ASIN"
              />
            </label>
            <button className="secondary-button" onClick={() => { setIsLoading(true); load(true).finally(() => setIsLoading(false)); }}>
              Refresh
            </button>
          </div>
        </div>
      </div>

      {/* ── Feedback ── */}
      {feedback && (
        <div className={`qfeedback qfeedback-${feedback.tone}`} onClick={() => setFeedback(null)}>
          {feedback.message}
        </div>
      )}

      {/* ── Empty state ── */}
      {visibleItems.length === 0 && allItems.length === 0 && (
        <div className="qempty">
          <strong>Queue is clear</strong>
          <span>No pending reviews right now.</span>
        </div>
      )}

      {visibleItems.length === 0 && allItems.length > 0 && (
        <div className="qempty">
          <strong>No matches</strong>
          <span>Try adjusting the filter or focus.</span>
        </div>
      )}

      {/* ── Card Grid ── */}
      {visibleItems.length > 0 && (
        <div className="qgrid">
          {visibleItems.map((item) => (
            <QueueCard
              key={item.id}
              item={item}
              isBusy={actionState?.reviewId === item.id}
              onApprove={() => void handleDecision(item.id, item.deal_id, "approve")}
              onReject={() => void handleDecision(item.id, item.deal_id, "reject")}
              onDetail={() => void openDetail(item.id, item.deal_id)}
            />
          ))}
        </div>
      )}

      {/* ── Load More ── */}
      {hasMore && (
        <div className="qload-more">
          <button className="secondary-button" onClick={() => void loadMore()} disabled={isLoadingMore}>
            {isLoadingMore ? "Loading…" : "Load more"}
          </button>
        </div>
      )}

      {/* ── Detail Drawer ── */}
      {detailReviewId && (
        <DetailDrawer
          reviewId={detailReviewId}
          deal={detailDeal}
          isLoading={isLoadingDetail}
          isBusy={actionState?.reviewId === detailReviewId}
          onClose={closeDetail}
          onApprove={() => void handleDecision(detailReviewId, detailDeal?.id ?? "", "approve")}
          onReject={() => void handleDecision(detailReviewId, detailDeal?.id ?? "", "reject")}
        />
      )}
    </div>
  );
}
