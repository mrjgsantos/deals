import { useEffect, useMemo, useRef, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import {
  getFeedPersonalizationSummary,
  getPersonalizationReasonLabel,
  getSavingsPercentValue,
} from "../lib/dealSignals";
import type { PublishedDeal, UserPreferences } from "../types";
import { CategoryScroller } from "../components/CategoryScroller";
import { DealCard } from "../components/DealCard";
import { DealCardSkeleton, HeroDealSkeleton } from "../components/DealCardSkeleton";
import { EmptyStatePanel } from "../components/EmptyStatePanel";
import { HeroDeal } from "../components/HeroDeal";
import { SectionBlock } from "../components/SectionBlock";

const INITIAL_COUNT = 24;
const PAGE_SIZE = 12;
const HERO_COUNT = 2;

function getQualityScore(deal: PublishedDeal): number {
  return deal.score_breakdown.quality_score ?? -1;
}

function hasFreshDrop(deal: PublishedDeal): boolean {
  return deal.score_breakdown.quality_reasons.includes("fresh_price_drop");
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
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);

  const loadMoreRef = useRef<HTMLDivElement | null>(null);
  const reportedImpressionsRef = useRef<Set<string>>(new Set());
  const isLoadingMoreRef = useRef(false);

  useEffect(() => {
    async function load() {
      setIsLoading(true);
      setError(null);
      try {
        const data = await api.getPublishedDealsPage(null, INITIAL_COUNT);
        setDeals(data.items);
        setNextCursor(data.next_cursor);
        setHasMoreDeals(data.has_more);
      } catch (e) {
        setError(getApiErrorMessage(e, "Não foi possível carregar os deals."));
      } finally {
        setIsLoading(false);
      }
    }
    void load();
  }, [refreshToken]);

  async function loadMoreDeals() {
    if (!hasMoreDeals || !nextCursor || isLoadingMoreRef.current) return;
    isLoadingMoreRef.current = true;
    setIsLoadingMore(true);
    try {
      const data = await api.getPublishedDealsPage(nextCursor, PAGE_SIZE);
      setDeals((current) => {
        const seen = new Set(current.map((d) => d.id));
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
    } catch (e) {
      setError(getApiErrorMessage(e, "Não foi possível carregar mais deals."));
    } finally {
      isLoadingMoreRef.current = false;
      setIsLoadingMore(false);
    }
  }

  // ---- Impression tracking ----
  useEffect(() => {
    const unseen = deals.filter((d) => !reportedImpressionsRef.current.has(d.id));
    if (unseen.length === 0) return;
    unseen.forEach((d) => reportedImpressionsRef.current.add(d.id));
    onImpression(unseen);
  }, [deals, onImpression]);

  // ---- Infinite scroll sentinel ----
  useEffect(() => {
    if (!hasMoreDeals) return;
    const target = loadMoreRef.current;
    if (!target) return;

    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          void loadMoreDeals();
        }
      },
      { rootMargin: "300px 0px" },
    );
    observer.observe(target);
    return () => observer.disconnect();
  }, [hasMoreDeals, nextCursor]);

  // ---- Derived sections ----
  const heroDeals = useMemo(() => {
    return [...deals]
      .filter((d) => getSavingsPercentValue(d) >= 10)
      .sort((a, b) => getQualityScore(b) - getQualityScore(a))
      .slice(0, HERO_COUNT);
  }, [deals]);

  const heroIds = useMemo(() => new Set(heroDeals.map((d) => d.id)), [heroDeals]);

  const recentDrops = useMemo(() => {
    return deals.filter((d) => hasFreshDrop(d) && !heroIds.has(d.id)).slice(0, 10);
  }, [deals, heroIds]);

  const forYouDeals = useMemo(() => {
    if (!preferences) return [];
    return deals
      .filter((d) => (d.personalization_score ?? 0) > 0 && !heroIds.has(d.id))
      .sort((a, b) => (b.personalization_score ?? 0) - (a.personalization_score ?? 0))
      .slice(0, 6);
  }, [deals, heroIds, preferences]);

  const categories = useMemo(() => {
    return [...new Set(deals.map((d) => d.category).filter((c): c is string => c != null))];
  }, [deals]);

  const personalizationSummary = useMemo(
    () => (preferences ? getFeedPersonalizationSummary(preferences) : null),
    [preferences],
  );

  // Base feed: exclude hero deals when no category is selected
  const feedDeals = useMemo(() => {
    if (selectedCategory) {
      return deals.filter((d) => d.category === selectedCategory);
    }
    return deals.filter((d) => !heroIds.has(d.id));
  }, [deals, heroIds, selectedCategory]);

  const showHero = !isLoading && !selectedCategory && heroDeals.length > 0;
  const showRecentDrops = !isLoading && !selectedCategory && recentDrops.length >= 2;
  const showForYou = !isLoading && !selectedCategory && forYouDeals.length >= 2;
  const showCategories = !isLoading && categories.length >= 2;

  return (
    <div className="d-feed">

      {/* ---- HERO ---- */}
      {isLoading ? (
        <section className="d-hero-section">
          <div className="d-hero-grid">
            <HeroDealSkeleton />
            <HeroDealSkeleton />
          </div>
        </section>
      ) : null}

      {showHero ? (
        <section className="d-hero-section">
          {personalizationSummary ? (
            <div className="d-hero-eyebrow">
              <span className="d-hero-label">✦ {personalizationSummary}</span>
            </div>
          ) : (
            <div className="d-hero-eyebrow">
              <span className="d-hero-label">✦ Melhores deals agora</span>
            </div>
          )}
          <div className="d-hero-grid">
            {heroDeals.map((deal) => (
              <HeroDeal
                key={deal.id}
                deal={deal}
                onViewDetails={(id) => navigate(`/deals/${id}`)}
                onOutboundClick={() => onOutboundClick(deal)}
              />
            ))}
          </div>
        </section>
      ) : null}

      {/* ---- CATEGORY FILTER ---- */}
      {showCategories ? (
        <CategoryScroller
          categories={categories}
          selected={selectedCategory}
          onSelect={setSelectedCategory}
        />
      ) : null}

      {/* ---- RECENT DROPS (horizontal scroll) ---- */}
      {showRecentDrops ? (
        <SectionBlock
          title="📉 Quedas Recentes"
          subtitle="Preços que baixaram nas últimas horas"
        >
          <div className="d-scroll-track">
            {recentDrops.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                isSaved={savedDealIds.has(deal.id)}
                isSavePending={pendingDealIds.has(deal.id)}
                personalizationLabel={preferences ? getPersonalizationReasonLabel(deal, preferences) : null}
                onToggleSave={() => onToggleSave(deal)}
                onOutboundClick={() => onOutboundClick(deal)}
                onViewDetails={(id) => navigate(`/deals/${id}`)}
              />
            ))}
          </div>
        </SectionBlock>
      ) : null}

      {/* ---- FOR YOU ---- */}
      {showForYou ? (
        <SectionBlock
          title="💡 Para ti"
          subtitle="Baseado nas tuas preferências e histórico"
        >
          <div className="d-cards-grid">
            {forYouDeals.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                isSaved={savedDealIds.has(deal.id)}
                isSavePending={pendingDealIds.has(deal.id)}
                personalizationLabel={getPersonalizationReasonLabel(deal, preferences!)}
                onToggleSave={() => onToggleSave(deal)}
                onOutboundClick={() => onOutboundClick(deal)}
                onViewDetails={(id) => navigate(`/deals/${id}`)}
              />
            ))}
          </div>
        </SectionBlock>
      ) : null}

      {/* ---- MAIN FEED ---- */}
      <SectionBlock
        title={selectedCategory ? `🏷 ${selectedCategory}` : "🔥 Top Deals"}
        subtitle={
          selectedCategory
            ? `Todos os deals em ${selectedCategory}`
            : "Os melhores deals de hoje, por score"
        }
        action={selectedCategory ? { label: "Ver todos", onClick: () => setSelectedCategory(null) } : undefined}
      >
        {isLoading ? (
          <div className="d-cards-grid" aria-label="A carregar deals" aria-busy="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <DealCardSkeleton key={`sk-${i}`} />
            ))}
          </div>
        ) : error ? (
          <div className="d-feed-error" role="alert">
            {error}
          </div>
        ) : feedDeals.length === 0 ? (
          <EmptyStatePanel
            title={selectedCategory ? `Sem deals em ${selectedCategory}` : "Sem deals publicados"}
            detail={
              selectedCategory
                ? "Tenta outra categoria ou remove o filtro."
                : "Novos deals aprovados aparecem aqui automaticamente."
            }
            actionLabel={selectedCategory ? "Ver todos os deals" : "Recarregar"}
            onAction={selectedCategory ? () => setSelectedCategory(null) : () => window.location.reload()}
          />
        ) : (
          <div className="d-cards-grid" aria-label="Feed de deals">
            {feedDeals.map((deal) => (
              <DealCard
                key={deal.id}
                deal={deal}
                isSaved={savedDealIds.has(deal.id)}
                isSavePending={pendingDealIds.has(deal.id)}
                personalizationLabel={preferences ? getPersonalizationReasonLabel(deal, preferences) : null}
                onToggleSave={() => onToggleSave(deal)}
                onOutboundClick={() => onOutboundClick(deal)}
                onViewDetails={(id) => navigate(`/deals/${id}`)}
              />
            ))}
            {hasMoreDeals ? (
              <div ref={loadMoreRef} className="public-feed-sentinel" aria-hidden="true" />
            ) : null}
            {isLoadingMore
              ? Array.from({ length: 3 }).map((_, i) => <DealCardSkeleton key={`more-${i}`} />)
              : null}
          </div>
        )}
      </SectionBlock>
    </div>
  );
}
