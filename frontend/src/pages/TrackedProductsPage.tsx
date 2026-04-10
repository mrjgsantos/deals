import { useEffect, useMemo, useState } from "react";

import { Badge, type BadgeTone } from "../components/Badge";
import { StatusMessage } from "../components/StatusMessage";
import { api, getApiErrorMessage } from "../lib/api";
import { formatDateTime, toTimestamp } from "../lib/format";
import type { TrackedProductItem, TrackedProductsResponse, TrackedProductsSchedulerStatus, TrackedProductsSummary } from "../types";

type TrackedSort = "attempt" | "status" | "history" | "asin";

const EMPTY_SUMMARY: TrackedProductsSummary = {
  total_tracked_products: 0,
  active_tracked_products: 0,
  never_attempted: 0,
  in_progress: 0,
  succeeded: 0,
  failed: 0,
  retry_backoff: 0,
  due_now: 0,
};

const EMPTY_SCHEDULER: TrackedProductsSchedulerStatus = {
  enabled: false,
  is_running: false,
  interval_seconds: null,
  last_started_at: null,
  last_completed_at: null,
  last_status: "disabled",
  last_error_reason: null,
  tracked_asins: null,
  eligible_asins: null,
  fetched_products: null,
  accepted: null,
  rejected: null,
  failed_batches: null,
  skipped_reason: null,
};

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong while talking to the API.");
}

function formatTimestamp(value: string | null): string {
  return formatDateTime(value);
}

function formatIntervalSeconds(value: number | null): string {
  if (value == null) {
    return "—";
  }
  if (value < 60) {
    return `${value}s`;
  }
  const minutes = Math.round(value / 60);
  return `${minutes}m`;
}

function getSchedulerTone(status: string): BadgeTone {
  if (status === "succeeded") {
    return "success";
  }
  if (status === "completed_with_failures" || status === "skipped" || status === "unavailable") {
    return "warning";
  }
  if (status === "failed" || status === "disabled") {
    return "danger";
  }
  return "neutral";
}

function getRefreshTone(status: string): BadgeTone {
  if (status === "succeeded") {
    return "success";
  }
  if (status === "fetch_failed" || status === "ingest_failed") {
    return "danger";
  }
  if (status === "in_progress") {
    return "warning";
  }
  return "neutral";
}

function getPriorityTone(priority: string): BadgeTone {
  if (priority === "urgent") {
    return "danger";
  }
  if (priority === "high") {
    return "warning";
  }
  if (priority === "normal") {
    return "neutral";
  }
  return "success";
}

function getStatusRank(status: string): number {
  const ranks: Record<string, number> = {
    fetch_failed: 0,
    ingest_failed: 1,
    in_progress: 2,
    never_attempted: 3,
    succeeded: 4,
  };
  return ranks[status] ?? 5;
}

function getLinkedBadges(item: TrackedProductItem): Array<{ value: string; tone: BadgeTone }> {
  const badges: Array<{ value: string; tone: BadgeTone }> = [];
  if (item.has_pending_review_deal) {
    badges.push({ value: "pending review", tone: "warning" });
  }
  if (item.has_published_deal) {
    badges.push({ value: "published", tone: "success" });
  }
  if (badges.length === 0 && item.linked_deal_count > 0) {
    badges.push({ value: "linked deal", tone: "neutral" });
  }
  return badges;
}

export function TrackedProductsPage() {
  const [summary, setSummary] = useState<TrackedProductsSummary>(EMPTY_SUMMARY);
  const [scheduler, setScheduler] = useState<TrackedProductsSchedulerStatus>(EMPTY_SCHEDULER);
  const [items, setItems] = useState<TrackedProductItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<TrackedSort>("attempt");

  async function loadTrackedProducts() {
    setIsLoading(true);
    setError(null);

    try {
      const data: TrackedProductsResponse = await api.getTrackedProducts();
      setSummary(data.summary);
      setScheduler(data.scheduler);
      setItems(data.items);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    void loadTrackedProducts();
  }, []);

  const visibleItems = useMemo(() => {
    return [...items].sort((left, right) => {
      if (sortBy === "status") {
        return (
          getStatusRank(left.refresh_status) - getStatusRank(right.refresh_status) ||
          left.asin.localeCompare(right.asin)
        );
      }
      if (sortBy === "history") {
        return (
          right.observation_count_all_time - left.observation_count_all_time ||
          (toTimestamp(right.last_refresh_attempt_at) ?? 0) - (toTimestamp(left.last_refresh_attempt_at) ?? 0)
        );
      }
      if (sortBy === "asin") {
        return left.asin.localeCompare(right.asin);
      }
      return (toTimestamp(left.last_refresh_attempt_at) ?? 0) - (toTimestamp(right.last_refresh_attempt_at) ?? 0);
    });
  }, [items, sortBy]);

  if (isLoading) {
    return <StatusMessage tone="info" title="Loading tracked products" detail="Fetching the tracked ASIN pool and latest Keepa refresh state." />;
  }

  if (error) {
    return <StatusMessage tone="error" title="Could not load tracked products" detail={error} />;
  }

  return (
    <div className="screen-layout">
      <div className="screen-header">
        <div>
          <div className="eyebrow">Keepa ops</div>
          <h1>Tracked Products</h1>
          <p className="screen-subtitle">Inspect the tracked ASIN pool, the latest refresh outcome, and where tracked products connect back into the deals flow.</p>
        </div>
        <div className="header-meta header-meta-stack">
          <span className="counter">{summary.total_tracked_products} tracked</span>
          <div className="filter-row">
            <label className="filter-control">
              <span>Sort</span>
              <select value={sortBy} onChange={(event) => setSortBy(event.target.value as TrackedSort)}>
                <option value="attempt">Oldest attempt first</option>
                <option value="status">Refresh status</option>
                <option value="history">Observation count</option>
                <option value="asin">ASIN</option>
              </select>
            </label>
            <button className="secondary-button" onClick={() => void loadTrackedProducts()}>
              Refresh
            </button>
          </div>
        </div>
      </div>

      <div className="ops-overview-grid">
        <section className="ops-panel">
          <div className="ops-panel-header">
            <div>
              <div className="eyebrow">Scheduler</div>
              <h3>Keepa Refresh</h3>
            </div>
            <Badge value={scheduler.last_status} tone={getSchedulerTone(scheduler.last_status)} />
          </div>
          <div className="ops-stats-grid">
            <div className="ops-stat">
              <span className="ops-stat-label">Enabled</span>
              <span className="ops-stat-value">{scheduler.enabled ? "Yes" : "No"}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Interval</span>
              <span className="ops-stat-value">{formatIntervalSeconds(scheduler.interval_seconds)}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Tracked in run</span>
              <span className="ops-stat-value">{scheduler.tracked_asins ?? "—"}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Eligible in run</span>
              <span className="ops-stat-value">{scheduler.eligible_asins ?? "—"}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Accepted</span>
              <span className="ops-stat-value">{scheduler.accepted ?? "—"}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Failed batches</span>
              <span className="ops-stat-value">{scheduler.failed_batches ?? "—"}</span>
            </div>
          </div>
          <div className="ops-meta-list">
            <span>Last started {formatTimestamp(scheduler.last_started_at)}</span>
            <span>Last completed {formatTimestamp(scheduler.last_completed_at)}</span>
            {scheduler.skipped_reason ? <span>Skipped: {scheduler.skipped_reason}</span> : null}
            {scheduler.last_error_reason ? <span>Error: {scheduler.last_error_reason}</span> : null}
          </div>
        </section>

        <section className="ops-panel">
          <div className="ops-panel-header">
            <div>
              <div className="eyebrow">Pool</div>
              <h3>Tracked Summary</h3>
            </div>
            <Badge value="tracked" tone="neutral" />
          </div>
          <div className="ops-stats-grid">
            <div className="ops-stat">
              <span className="ops-stat-label">Total</span>
              <span className="ops-stat-value">{summary.total_tracked_products}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Never attempted</span>
              <span className="ops-stat-value">{summary.never_attempted}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">In progress</span>
              <span className="ops-stat-value">{summary.in_progress}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Succeeded</span>
              <span className="ops-stat-value">{summary.succeeded}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Failed</span>
              <span className="ops-stat-value">{summary.failed}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Retry backoff</span>
              <span className="ops-stat-value">{summary.retry_backoff}</span>
            </div>
            <div className="ops-stat">
              <span className="ops-stat-label">Due now</span>
              <span className="ops-stat-value">{summary.due_now}</span>
            </div>
          </div>
        </section>
      </div>

      {items.length === 0 ? (
        <div className="empty-state-shell">
          <StatusMessage tone="info" title="No tracked products yet" detail="Tracked ASINs will appear here once deal generation links an Amazon product into the tracked pool." />
        </div>
      ) : (
        <div className="table-shell">
          <table className="deals-table">
            <thead>
              <tr>
                <th>ASIN</th>
                <th>Product</th>
                <th>Source</th>
                <th>Refresh</th>
                <th>History</th>
                <th>Linked flow</th>
              </tr>
            </thead>
            <tbody>
              {visibleItems.map((item) => {
                const linkedBadges = getLinkedBadges(item);

                return (
                  <tr key={item.id}>
                    <td>
                      <div className="table-title">{item.asin}</div>
                      <div className="table-subtitle">Domain {item.domain_id}</div>
                      <div className="badge-cluster badge-cluster-wrap">
                        <Badge value={item.is_active ? "tracked" : "inactive"} tone={item.is_active ? "success" : "danger"} />
                      </div>
                    </td>
                    <td className="table-title-cell">
                      <div className="table-title">{item.display_name ?? "No linked display name yet"}</div>
                      <div className="table-subtitle">
                        {item.source_url ? (
                          <a className="ops-table-link" href={item.source_url} target="_blank" rel="noreferrer">
                            Open latest source record
                          </a>
                        ) : (
                          "Latest source record not available."
                        )}
                      </div>
                    </td>
                    <td>
                      <div>{item.source_name ?? "—"}</div>
                      <div className="table-subtitle">{item.source_slug ?? "No source slug"}</div>
                    </td>
                    <td>
                      <div className="badge-cluster badge-cluster-wrap">
                        <Badge value={item.refresh_status} tone={getRefreshTone(item.refresh_status)} />
                        <Badge value={item.refresh_priority} tone={getPriorityTone(item.refresh_priority)} />
                        <Badge value={item.staleness_classification} tone="neutral" />
                      </div>
                      <div className="table-subtitle">Attempt {formatTimestamp(item.last_refresh_attempt_at)}</div>
                      <div className="table-subtitle">Success {formatTimestamp(item.last_successful_refresh_at)}</div>
                      <div className="table-subtitle">Failure {formatTimestamp(item.last_failed_refresh_at)}</div>
                      <div className="table-subtitle">Earliest next {formatTimestamp(item.next_refresh_earliest_at)}</div>
                      <div className="table-subtitle">Failure streak {item.consecutive_refresh_failures}</div>
                      {item.refresh_failure_reason ? (
                        <div className="table-subtitle">Failure: {item.refresh_failure_reason}</div>
                      ) : null}
                    </td>
                    <td>
                      <div>{item.observation_count_all_time} observations</div>
                    </td>
                    <td>
                      <div>{item.linked_deal_count} linked deal{item.linked_deal_count === 1 ? "" : "s"}</div>
                      <div className="badge-cluster badge-cluster-wrap">
                        {linkedBadges.length > 0 ? linkedBadges.map((badge) => <Badge key={badge.value} value={badge.value} tone={badge.tone} />) : <Badge value="no linked deal" tone="neutral" />}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
