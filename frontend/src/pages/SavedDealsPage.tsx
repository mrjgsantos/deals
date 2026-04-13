import { useMemo } from "react";

import { EmptyStatePanel } from "../components/EmptyStatePanel";
import { PublicDealCard } from "../components/PublicDealCard";
import { StatusMessage } from "../components/StatusMessage";
import { toTimestamp } from "../lib/format";
import type { PublishedDeal, SavedDealItem } from "../types";

export function SavedDealsPage({
  items,
  isLoading,
  error,
  navigate,
  savedDealIds,
  pendingDealIds,
  onToggleSave,
}: {
  items: SavedDealItem[];
  isLoading: boolean;
  error: string | null;
  navigate: (path: string) => void;
  savedDealIds: Set<string>;
  pendingDealIds: Set<string>;
  onToggleSave: (deal: PublishedDeal) => void;
}) {
  const visibleItems = useMemo(() => {
    return [...items].sort((left, right) => {
      const leftTime = toTimestamp(left.saved_at) ?? 0;
      const rightTime = toTimestamp(right.saved_at) ?? 0;
      return rightTime - leftTime;
    });
  }, [items]);

  return (
    <div className="public-shell">
      <section className="public-hero">
        <div className="eyebrow">Saved deals</div>
        <h1 className="public-hero-title">Keep the deals you want to revisit close at hand.</h1>
        <p className="public-hero-copy">Saved deals stay here so you can compare later without hunting through the feed again.</p>
      </section>

      {isLoading ? <StatusMessage tone="info" title="Loading saved deals" detail="Pulling your saved list." /> : null}
      {!isLoading && error ? <StatusMessage tone="error" title="Could not load saved deals" detail={error} /> : null}
      {!isLoading && !error && visibleItems.length === 0 ? (
        <div className="public-empty-state">
          <EmptyStatePanel
            title="No saved deals yet"
            detail="Tap the heart on any published deal and it will show up here for quick access later."
            actionLabel="Explore deals"
            onAction={() => navigate("/")}
          />
        </div>
      ) : null}

      {!isLoading && !error && visibleItems.length > 0 ? (
        <section className="public-feed-grid" aria-label="Saved deals">
          {visibleItems.map((item) => (
            <PublicDealCard
              key={item.deal.id}
              deal={item.deal}
              isSaved={savedDealIds.has(item.deal.id)}
              isSavePending={pendingDealIds.has(item.deal.id)}
              onToggleSave={() => onToggleSave(item.deal)}
              onViewDetails={(dealId) => navigate(`/deals/${dealId}`)}
            />
          ))}
        </section>
      ) : null}
    </div>
  );
}
