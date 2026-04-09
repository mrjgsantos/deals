import { useEffect, useState } from "react";

import { api, ApiError } from "../lib/api";
import type { Deal } from "../types";
import { Badge } from "../components/Badge";
import { DealSummary } from "../components/DealSummary";
import { StatusMessage } from "../components/StatusMessage";
import { formatDateTime, formatMoney } from "../lib/format";

function getErrorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    return `Request failed: ${error.message}`;
  }
  return "Something went wrong while talking to the API.";
}

export function DealsPage() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [selectedDeal, setSelectedDeal] = useState<Deal | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

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
        <span className="counter">{deals.length} deals</span>
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
                {deals.map((deal) => (
                  <tr key={deal.id} className={deal.id === selectedDeal?.id ? "row-active" : ""}>
                    <td>
                      <Badge value={deal.status} />
                    </td>
                    <td className="table-title-cell">
                      <div className="table-title">{deal.title}</div>
                      <div className="table-subtitle">{deal.summary ?? "No summary provided."}</div>
                    </td>
                    <td>{formatMoney(deal.current_price, deal.currency)}</td>
                    <td>{formatDateTime(deal.detected_at)}</td>
                    <td>
                      <button className="inline-button" onClick={() => void inspectDeal(deal.id)}>
                        Inspect
                      </button>
                    </td>
                  </tr>
                ))}
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
