import { useEffect, useMemo, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { PublishedDeal } from "../types";
import { PublicDealCard } from "../components/PublicDealCard";
import { StatusMessage } from "../components/StatusMessage";
import { toTimestamp } from "../lib/format";

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong while loading the latest published deals.");
}

export function PublicDealsFeedPage({
  navigate,
}: {
  navigate: (path: string) => void;
}) {
  const [deals, setDeals] = useState<PublishedDeal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadPublishedDeals() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getPublishedDeals();
        setDeals(data);
      } catch (loadError) {
        setError(getErrorMessage(loadError));
      } finally {
        setIsLoading(false);
      }
    }

    void loadPublishedDeals();
  }, []);

  const visibleDeals = useMemo(() => {
    return [...deals].sort((left, right) => {
      const leftTime = toTimestamp(left.published_at ?? left.detected_at) ?? 0;
      const rightTime = toTimestamp(right.published_at ?? right.detected_at) ?? 0;
      return rightTime - leftTime;
    });
  }, [deals]);

  return (
    <div className="public-shell">
      <section className="public-hero">
        <div className="eyebrow">Published deals</div>
        <h1 className="public-hero-title">Fresh savings with real price history behind them.</h1>
        <p className="public-hero-copy">
          Browse the latest approved and published deals, with cleaner pricing context and a direct path to the merchant.
        </p>
      </section>

      {isLoading ? (
        <StatusMessage tone="info" title="Loading published deals" detail="Pulling the latest live offers." />
      ) : null}

      {!isLoading && error ? (
        <StatusMessage tone="error" title="Could not load published deals" detail={error} />
      ) : null}

      {!isLoading && !error && visibleDeals.length === 0 ? (
        <div className="public-empty-state">
          <StatusMessage
            tone="info"
            title="No published deals yet"
            detail="Once approved deals are published, they will appear here automatically."
          />
        </div>
      ) : null}

      {!isLoading && !error && visibleDeals.length > 0 ? (
        <section className="public-feed-grid" aria-label="Published deals">
          {visibleDeals.map((deal) => (
            <PublicDealCard key={deal.id} deal={deal} onViewDetails={(dealId) => navigate(`/deals/${dealId}`)} />
          ))}
        </section>
      ) : null}
    </div>
  );
}
