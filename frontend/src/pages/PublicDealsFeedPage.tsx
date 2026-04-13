import { useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import type { PublishedDeal, UserPreferences } from "../types";
import { EmptyStatePanel } from "../components/EmptyStatePanel";
import { PublicDealCard } from "../components/PublicDealCard";
import { PublicDealCardSkeleton } from "../components/PublicDealCardSkeleton";
import { StatusMessage } from "../components/StatusMessage";
import { getFeedPersonalizationSummary, getPersonalizationReasonLabel } from "../lib/dealSignals";
const INITIAL_FEED_COUNT = 12;
const FEED_PAGE_SIZE = 12;
const FEED_SKELETON_COUNT = 6;

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong while loading the latest published deals.");
}

export function PublicDealsFeedPage({
  navigate,
  savedDealIds,
  pendingDealIds,
  onToggleSave,
  onOutboundClick,
  onImpression,
  preferences,
  refreshToken,
}: {
  navigate: (path: string) => void;
  savedDealIds: Set<string>;
  pendingDealIds: Set<string>;
  onToggleSave: (deal: PublishedDeal) => void;
  onOutboundClick: (deal: PublishedDeal) => void;
  onImpression: (deals: PublishedDeal[]) => void;
  preferences: UserPreferences | null;
  refreshToken: number;
}) {
  const [deals, setDeals] = useState<PublishedDeal[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [hasMoreDeals, setHasMoreDeals] = useState(false);
  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const reportedImpressionsRef = useRef<Set<string>>(new Set());
  const isLoadingMoreRef = useRef(false);

  useEffect(() => {
    async function loadPublishedDeals() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getPublishedDealsPage(null, INITIAL_FEED_COUNT);
        setDeals(data.items);
        setNextCursor(data.next_cursor);
        setHasMoreDeals(data.has_more);
      } catch (loadError) {
        setError(getErrorMessage(loadError));
      } finally {
        setIsLoading(false);
      }
    }

    void loadPublishedDeals();
  }, [refreshToken]);

  async function refreshPublishedDeals() {
    setIsLoading(true);
    setError(null);

    try {
      const data = await api.getPublishedDealsPage(null, INITIAL_FEED_COUNT);
      setDeals(data.items);
      setNextCursor(data.next_cursor);
      setHasMoreDeals(data.has_more);
      reportedImpressionsRef.current.clear();
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      setIsLoading(false);
    }
  }

  async function loadMoreDeals() {
    if (!hasMoreDeals || !nextCursor || isLoadingMoreRef.current) {
      return;
    }
    isLoadingMoreRef.current = true;
    setIsLoadingMore(true);
    try {
      const data = await api.getPublishedDealsPage(nextCursor, FEED_PAGE_SIZE);
      setDeals((current) => {
        const seen = new Set(current.map((deal) => deal.id));
        const merged = [...current];
        for (const deal of data.items) {
          if (!seen.has(deal.id)) {
            seen.add(deal.id);
            merged.push(deal);
          }
        }
        return merged;
      });
      setNextCursor(data.next_cursor);
      setHasMoreDeals(data.has_more);
    } catch (loadError) {
      setError(getErrorMessage(loadError));
    } finally {
      isLoadingMoreRef.current = false;
      setIsLoadingMore(false);
    }
  }

  const renderedDeals = useMemo(() => deals, [deals]);
  const personalizationSummary = useMemo(
    () => (preferences ? getFeedPersonalizationSummary(preferences) : null),
    [preferences],
  );

  useEffect(() => {
    const unseenDeals = renderedDeals.filter((deal) => !reportedImpressionsRef.current.has(deal.id));
    if (unseenDeals.length === 0) {
      return;
    }
    unseenDeals.forEach((deal) => reportedImpressionsRef.current.add(deal.id));
    onImpression(unseenDeals);
  }, [renderedDeals, onImpression]);

  useEffect(() => {
    if (!hasMoreDeals) {
      return;
    }

    const target = loadMoreRef.current;
    if (!target) {
      return;
    }

    const observer = new IntersectionObserver(
      (entries) => {
        if (!entries.some((entry) => entry.isIntersecting)) {
          return;
        }
        void loadMoreDeals();
      },
      {
        rootMargin: "240px 0px",
      },
    );

    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMoreDeals, nextCursor]);

  return (
    <div className="public-shell">
      <section className="public-hero">
        <div className="eyebrow">Published deals</div>
        <h1 className="public-hero-title">Fresh savings with real price history behind them.</h1>
        <p className="public-hero-copy">
          Browse the latest approved and published deals, with cleaner pricing context and a direct path to the merchant.
        </p>
        {personalizationSummary ? <div className="public-subtle-label">{personalizationSummary}</div> : null}
      </section>

      {isLoading ? (
        <section className="public-feed-grid" aria-label="Loading published deals" aria-busy="true">
          {Array.from({ length: FEED_SKELETON_COUNT }).map((_, index) => (
            <PublicDealCardSkeleton key={`feed-skeleton-${index}`} />
          ))}
        </section>
      ) : null}

      {!isLoading && error ? (
        <StatusMessage tone="error" title="Could not load published deals" detail={error} />
      ) : null}

      {!isLoading && !error && renderedDeals.length === 0 ? (
        <div className="public-empty-state">
          <EmptyStatePanel
            title="No published deals yet"
            detail="There are no live deals to show right now. New approved deals will appear here automatically."
            actionLabel="Refresh deals"
            onAction={() => void refreshPublishedDeals()}
          />
        </div>
      ) : null}

      {!isLoading && !error && renderedDeals.length > 0 ? (
        <section className="public-feed-grid" aria-label="Published deals">
          {renderedDeals.map((deal) => (
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
          {hasMoreDeals ? <div ref={loadMoreRef} className="public-feed-sentinel" aria-hidden="true" /> : null}
          {isLoadingMore
            ? Array.from({ length: 2 }).map((_, index) => <PublicDealCardSkeleton key={`feed-more-${index}`} />)
            : null}
        </section>
      ) : null}
    </div>
  );
}
