import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { Deal, DealsListItem, DealsListPage } from "../types";
import { DealSummary } from "../components/DealSummary";
import { PriceBar } from "../components/PriceBar";
import { formatMoney, formatPercent, formatRelativeTime } from "../lib/format";
import { getSourceLabel, getSourceLinkType } from "../lib/dealSignals";

// ─── Types ────────────────────────────────────────────────────────────────────

type Filters = {
  status: string;
  source: string;
  minScore: string;
  minSavings: string;
  sinceDays: string;
  fakeDiscountOnly: boolean;
  sortBy: string;
};

const DEFAULT_FILTERS: Filters = {
  status: "",
  source: "",
  minScore: "",
  minSavings: "",
  sinceDays: "",
  fakeDiscountOnly: false,
  sortBy: "newest",
};

const LIMIT = 50;

// ─── Helpers ──────────────────────────────────────────────────────────────────

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong.");
}

function itemSourceLabel(item: DealsListItem): string {
  if (item.asin) return "Amazon";
  const label = getSourceLabel(item.deal_url);
  return label ?? item.source_category ?? "Unknown";
}

function isAmazon(item: DealsListItem): boolean {
  return Boolean(item.asin);
}

function buildFiltersForApi(filters: Filters) {
  return {
    status: filters.status || undefined,
    source: filters.source || undefined,
    minScore: filters.minScore ? parseInt(filters.minScore, 10) : undefined,
    minSavings: filters.minSavings ? parseFloat(filters.minSavings) : undefined,
    sinceDays: filters.sinceDays ? parseInt(filters.sinceDays, 10) : undefined,
    fakeDiscountOnly: filters.fakeDiscountOnly || undefined,
    sortBy: filters.sortBy || undefined,
  };
}

// ─── Status Badge ─────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`deal-status-badge deal-status-${status}`}>
      {status.replace("_", " ")}
    </span>
  );
}

// ─── Deal Card ────────────────────────────────────────────────────────────────

function DealCard({
  item,
  onDetail,
}: {
  item: DealsListItem;
  onDetail: () => void;
}) {
  const src = itemSourceLabel(item);
  const amazon = isAmazon(item);
  const linkType = getSourceLinkType(item.deal_url);
  const score = item.quality_score;
  const hasDiscount = item.savings_percent !== null && parseFloat(item.savings_percent ?? "0") > 0;
  const highScore = score !== null && score >= 70;
  const lowScore = score !== null && score < 50;

  return (
    <article className="qcard">
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
            <StatusBadge status={item.status} />
            <span className={`qcard-source-badge${amazon ? " qcard-source-amazon" : " qcard-source-google"}`}>
              {amazon ? "Amazon" : src}
            </span>
            {score !== null && (
              <span className={`qcard-score${highScore ? " qcard-score-high" : lowScore ? " qcard-score-low" : ""}`}>
                Q{score}
              </span>
            )}
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
        <span className="qcard-age">{formatRelativeTime(item.detected_at)}</span>
        <div className="qcard-actions">
          <button className="qcard-btn-detail" onClick={onDetail} title="Open full deal detail">
            Detail
          </button>
        </div>
      </div>
    </article>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function DealsSkeleton() {
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
  deal,
  isLoading,
  onClose,
}: {
  deal: Deal | null;
  isLoading: boolean;
  onClose: () => void;
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
        </div>
        <div className="drawer-body">
          {isLoading && <div className="drawer-loading">Loading deal details…</div>}
          {!isLoading && deal && <DealSummary deal={deal} />}
        </div>
      </div>
    </>
  );
}

// ─── Filter Bar ───────────────────────────────────────────────────────────────

function FilterBar({
  filters,
  onChange,
  onRefresh,
  isLoading,
}: {
  filters: Filters;
  onChange: (patch: Partial<Filters>) => void;
  onRefresh: () => void;
  isLoading: boolean;
}) {
  return (
    <div className="filter-row deals-filter-row">
      <label className="filter-control">
        <span>Status</span>
        <select value={filters.status} onChange={(e) => onChange({ status: e.target.value })}>
          <option value="">All statuses</option>
          <option value="pending_review">Pending review</option>
          <option value="approved">Approved</option>
          <option value="published">Published</option>
          <option value="rejected">Rejected</option>
        </select>
      </label>
      <label className="filter-control">
        <span>Source</span>
        <select value={filters.source} onChange={(e) => onChange({ source: e.target.value })}>
          <option value="">All sources</option>
          <option value="amazon">Amazon</option>
          <option value="google">Google</option>
        </select>
      </label>
      <label className="filter-control">
        <span>Period</span>
        <select value={filters.sinceDays} onChange={(e) => onChange({ sinceDays: e.target.value })}>
          <option value="">All time</option>
          <option value="1">Last 24h</option>
          <option value="7">Last 7 days</option>
          <option value="30">Last 30 days</option>
        </select>
      </label>
      <label className="filter-control">
        <span>Sort</span>
        <select value={filters.sortBy} onChange={(e) => onChange({ sortBy: e.target.value })}>
          <option value="newest">Newest</option>
          <option value="score">Score</option>
          <option value="savings">Savings %</option>
        </select>
      </label>
      <label className="filter-control filter-control-narrow">
        <span>Min score</span>
        <input
          type="number"
          min={0}
          max={100}
          value={filters.minScore}
          onChange={(e) => onChange({ minScore: e.target.value })}
          placeholder="0–100"
        />
      </label>
      <label className="filter-control filter-control-narrow">
        <span>Min savings %</span>
        <input
          type="number"
          min={0}
          max={100}
          value={filters.minSavings}
          onChange={(e) => onChange({ minSavings: e.target.value })}
          placeholder="0–100"
        />
      </label>
      <label className="filter-control filter-control-inline">
        <input
          type="checkbox"
          checked={filters.fakeDiscountOnly}
          onChange={(e) => onChange({ fakeDiscountOnly: e.target.checked })}
        />
        <span>Fake discount</span>
      </label>
      <button className="secondary-button" onClick={onRefresh} disabled={isLoading}>
        {isLoading ? "…" : "Refresh"}
      </button>
    </div>
  );
}

// ─── Main Page ────────────────────────────────────────────────────────────────

export function DealsPage() {
  const [pages, setPages] = useState<DealsListPage[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filters, setFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [pendingFilters, setPendingFilters] = useState<Filters>(DEFAULT_FILTERS);
  const [detailDeal, setDetailDeal] = useState<Deal | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  const allItems = useMemo(() => pages.flatMap((p) => p.items), [pages]);
  const offset = allItems.length;

  async function load(activeFilters: Filters, replace = true) {
    try {
      const page = await api.getDealsListPage(buildFiltersForApi(activeFilters), replace ? 0 : 0, LIMIT);
      setPages([page]);
      setHasMore(page.has_more);
    } catch (err) {
      setError(getErrorMessage(err));
    }
  }

  async function loadMore() {
    setIsLoadingMore(true);
    try {
      const page = await api.getDealsListPage(buildFiltersForApi(filters), offset, LIMIT);
      setPages((prev) => [...prev, page]);
      setHasMore(page.has_more);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoadingMore(false);
    }
  }

  // Apply filters on change with a short debounce for number inputs
  const applyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function handleFilterChange(patch: Partial<Filters>) {
    const next = { ...pendingFilters, ...patch };
    setPendingFilters(next);

    const isNumericChange = patch.minScore !== undefined || patch.minSavings !== undefined;
    const delay = isNumericChange ? 600 : 0;

    if (applyTimer.current) clearTimeout(applyTimer.current);
    applyTimer.current = setTimeout(() => {
      setFilters(next);
      setIsLoading(true);
      load(next, true).finally(() => setIsLoading(false));
    }, delay);
  }

  useEffect(() => {
    load(DEFAULT_FILTERS, true).finally(() => setIsLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openDetail = useCallback(async (dealId: string) => {
    setIsDetailOpen(true);
    setDetailDeal(null);
    setIsLoadingDetail(true);
    try {
      const deal = await api.getDeal(dealId);
      setDetailDeal(deal);
    } catch {
      // drawer shows loading state
    } finally {
      setIsLoadingDetail(false);
    }
  }, []);

  const closeDetail = useCallback(() => {
    setIsDetailOpen(false);
    setDetailDeal(null);
  }, []);

  const summary = useMemo(() => ({
    total: allItems.length,
    amazon: allItems.filter((i) => Boolean(i.asin)).length,
    fakeDiscount: allItems.filter((i) => i.fake_discount).length,
    highScore: allItems.filter((i) => (i.quality_score ?? 0) >= 65).length,
  }), [allItems]);

  if (isLoading && pages.length === 0) {
    return (
      <div className="screen-layout">
        <div className="screen-header">
          <div>
            <div className="eyebrow">Deals</div>
            <h1>All Deals</h1>
          </div>
        </div>
        <DealsSkeleton />
      </div>
    );
  }

  if (error) {
    return (
      <div className="screen-layout">
        <div className="screen-header">
          <div>
            <div className="eyebrow">Deals</div>
            <h1>All Deals</h1>
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
          <div className="eyebrow">Deals</div>
          <h1>All Deals</h1>
        </div>
        <div className="header-meta header-meta-stack">
          <div className="qstats-row">
            <span className="qstat">{summary.total} loaded</span>
            {summary.amazon > 0 && <span className="qstat qstat-amazon">{summary.amazon} Amazon</span>}
            {summary.fakeDiscount > 0 && <span className="qstat qstat-danger">{summary.fakeDiscount} fake discount risk</span>}
            {summary.highScore > 0 && <span className="qstat qstat-success">{summary.highScore} score 65+</span>}
          </div>
          <FilterBar
            filters={pendingFilters}
            onChange={handleFilterChange}
            onRefresh={() => {
              setIsLoading(true);
              load(filters, true).finally(() => setIsLoading(false));
            }}
            isLoading={isLoading}
          />
        </div>
      </div>

      {/* ── Loading overlay ── */}
      {isLoading && pages.length > 0 && (
        <div className="qfeedback qfeedback-info">Loading…</div>
      )}

      {/* ── Empty ── */}
      {!isLoading && allItems.length === 0 && (
        <div className="qempty">
          <strong>No deals found</strong>
          <span>Try adjusting the filters.</span>
        </div>
      )}

      {/* ── Card Grid ── */}
      {allItems.length > 0 && (
        <div className="qgrid">
          {allItems.map((item) => (
            <DealCard
              key={item.id}
              item={item}
              onDetail={() => void openDetail(item.id)}
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
      {isDetailOpen && (
        <DetailDrawer
          deal={detailDeal}
          isLoading={isLoadingDetail}
          onClose={closeDetail}
        />
      )}
    </div>
  );
}
