import { useEffect, useMemo, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { Deal } from "../types";
import { Badge } from "../components/Badge";
import { DealSummary } from "../components/DealSummary";
import { StatusMessage } from "../components/StatusMessage";
import { formatDateTime, formatMoney, formatPercent, toTimestamp } from "../lib/format";
import { getHistorySupportSummary, getPublicationReadiness, getQualityScore, getSavingsPercentValue, getSourceLabel } from "../lib/dealSignals";

type DealSort = "newest" | "score" | "savings" | "status";

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong while talking to the API.");
}

export function DealsPage() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [sortBy, setSortBy] = useState<DealSort>("newest");

  useEffect(() => {
    async function loadDeals() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getDeals();
        setDeals(data);
        setSelectedDeal(data[0] ?? null);
      } catch (loadError) {
        setError(getErrorMessage(loadError));
      } finally {
        setIsLoading(false);
      }
    }

    void loadDeals();
  }, []);

  async function inspectDeal(id: string) {
    try {
      const detail = await api.getDeal(id);
      setSelectedDeal(detail);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    }
  }

  const visibleDeals = useMemo(() => {
    return [...deals].sort((left, right) => {
      if (sortBy === "score") {
        return getQualityScore(right) - getQualityScore(left);
      }
      if (sortBy === "savings") {
        return getSavingsPercentValue(right) - getSavingsPercentValue(left);
      }
      if (sortBy === "status") {
        return left.status.localeCompare(right.status) || (toTimestamp(right.detected_at) ?? 0) - (toTimestamp(left.detected_at) ?? 0);
      }
      return (toTimestamp(right.detected_at) ?? 0) - (toTimestamp(left.detected_at) ?? 0);
    });
  }, [deals, sortBy]);

  useEffect(() => {
    if (!selectedDeal && visibleDeals[0]) {
      setSelectedDeal(visibleDeals[0]);
      return;
    }

    if (selectedDeal && !visibleDeals.some((deal) => deal.id === selectedDeal.id)) {
      setSelectedDeal(visibleDeals[0] ?? null);
    }
  }, [selectedDeal, visibleDeals]);

  if (isLoading) {
    return <StatusMessage tone="info" title="Loading deals" detail="Fetching current deals from the API." />;
  }

  if (error) {
    return <StatusMessage tone="error" title="Could not load deals" detail={error} />;
  }

  return (
    <div className="screen-layout">
      <div className="screen-header">
        <div>
          <div className="eyebrow">Deals</div>
          <h1>Current Deals</h1>
          <p className="screen-subtitle">Browse current deal records and inspect the latest detail payload.</p>
        </div>
        <div className="header-meta">
          <span className="counter">{deals.length} deals</span>
          <label className="filter-control">
            <span>Sort</span>
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value as DealSort)}>
              <option value="newest">Newest</option>
              <option value="score">Score</option>
              <option value="savings">Savings %</option>
              <option value="status">Status</option>
            </select>
          </label>
        </div>
      </div>

      {deals.length === 0 ? (
        <div className="empty-state-shell">
          <StatusMessage tone="info" title="No deals available" detail="Run ingestion to populate the deals table." />
        </div>
      ) : (
        <div className="deals-layout">
          <div className="table-shell">
            <table className="deals-table">
              <thead>
                <tr>
                  <th>Status</th>
                  <th>Title</th>
                  <th>Current price</th>
                  <th>Detected</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {visibleDeals.map((deal) => {
                  const publicationState = getPublicationReadiness(deal);
                  const sourceLabel = getSourceLabel(deal.deal_url);

                  return (
                  <tr key={deal.id} className={deal.id === selectedDeal?.id ? "row-active" : ""}>
                    <td>
                      <div className="badge-cluster badge-cluster-wrap">
                        <Badge value={deal.status} />
                        <Badge value={publicationState.label} tone={publicationState.tone} />
                      </div>
                    </td>
                    <td className="table-title-cell">
                      <div className="table-title">{deal.title}</div>
                      <div className="table-subtitle">
                        {deal.summary ?? "No summary provided."}
                        {sourceLabel ? ` • ${sourceLabel}` : ""}
                      </div>
                    </td>
                    <td>
                      <div>{formatMoney(deal.current_price, deal.currency)}</div>
                      <div className="table-subtitle">
                        {formatMoney(deal.previous_price, deal.currency)} baseline • {formatPercent(deal.savings_percent)}
                      </div>
                      <div className="table-subtitle">
                        Save {formatMoney(deal.savings_amount, deal.currency)} • Q{deal.score_breakdown.quality_score ?? "—"}
                      </div>
                    </td>
                    <td>
                      <div>{formatDateTime(deal.detected_at)}</div>
                      <div className="table-subtitle">{getHistorySupportSummary(deal)}</div>
                    </td>
                    <td>
                      <button className="inline-button" onClick={() => void inspectDeal(deal.id)}>
                        Inspect
                      </button>
                    </td>
                  </tr>
                )})}
              </tbody>
            </table>
          </div>

          {selectedDeal ? (
            <section className="deal-detail-panel">
              <DealSummary deal={selectedDeal} />
            </section>
          ) : null}
        </div>
      )}
    </div>
  );
}
