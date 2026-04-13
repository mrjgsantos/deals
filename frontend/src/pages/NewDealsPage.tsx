import { useEffect, useRef } from "react";

import { EmptyStatePanel } from "../components/EmptyStatePanel";
import { PublicDealCard } from "../components/PublicDealCard";
import { StatusMessage } from "../components/StatusMessage";
import { getPersonalizationReasonLabel } from "../lib/dealSignals";
import type { PublishedDeal, UserPreferences } from "../types";

export function NewDealsPage({
  deals,
  newCount,
  fallbackUsed,
  lastSeenAt,
  isLoading,
  error,
  navigate,
  savedDealIds,
  pendingDealIds,
  onToggleSave,
  onOutboundClick,
  onImpression,
  preferences,
}: {
  deals: PublishedDeal[];
  newCount: number;
  fallbackUsed: boolean;
  lastSeenAt: string | null;
  isLoading: boolean;
  error: string | null;
  navigate: (path: string) => void;
  savedDealIds: Set<string>;
  pendingDealIds: Set<string>;
  onToggleSave: (deal: PublishedDeal) => void;
  onOutboundClick: (deal: PublishedDeal) => void;
  onImpression: (deals: PublishedDeal[]) => void;
  preferences: UserPreferences | null;
}) {
  const reportedImpressionsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const unseenDeals = deals.filter((deal) => !reportedImpressionsRef.current.has(deal.id));
    if (unseenDeals.length === 0) {
      return;
    }
    unseenDeals.forEach((deal) => reportedImpressionsRef.current.add(deal.id));
    onImpression(unseenDeals);
  }, [deals, onImpression]);

  const detail = fallbackUsed
    ? lastSeenAt
      ? "Nothing new has landed since your last visit, so we’re showing your best personalized deals instead."
      : "Open this view once and we’ll start tracking what’s new since your last visit."
    : "Freshly published deals are ranked for you first, with a short-lived newness boost on top of your usual personalization."

  return (
    <div className="public-shell">
      <section className="public-hero">
        <div className="eyebrow">New for you</div>
        <h1 className="public-hero-title">Come back to the deals that changed since your last visit.</h1>
        <p className="public-hero-copy">{detail}</p>
      </section>

      {isLoading ? <StatusMessage tone="info" title="Loading new deals" detail="Checking what changed since your last visit." /> : null}
      {!isLoading && error ? <StatusMessage tone="error" title="Could not load new deals" detail={error} /> : null}

      {!isLoading && !error ? (
        <div className="badge-cluster badge-cluster-wrap">
          <span className="public-recommended-badge">{newCount > 0 ? `${newCount} new deals for you` : "No new deals right now"}</span>
          {fallbackUsed ? <span className="public-meta-text">Showing your best personalized fallback</span> : null}
        </div>
      ) : null}

      {!isLoading && !error && deals.length === 0 ? (
        <div className="public-empty-state">
          <EmptyStatePanel
            title="No new deals for you right now"
            detail="We’re not seeing anything fresh yet, so the best move is to check the latest personalized deals."
            actionLabel="Explore latest deals"
            onAction={() => navigate("/")}
          />
        </div>
      ) : null}

      {!isLoading && !error && deals.length > 0 ? (
        <section className="public-feed-grid" aria-label="New deals for you">
          {deals.map((deal) => (
            <PublicDealCard
              key={deal.id}
              deal={deal}
              isSaved={savedDealIds.has(deal.id)}
              isSavePending={pendingDealIds.has(deal.id)}
              personalizationLabel={preferences ? getPersonalizationReasonLabel(deal, preferences) : null}
              onToggleSave={() => onToggleSave(deal)}
              onOutboundClick={() => onOutboundClick(deal)}
              onViewDetails={(dealId) => navigate(`/deals/${dealId}`)}
            />
          ))}
        </section>
      ) : null}
    </div>
  );
}
