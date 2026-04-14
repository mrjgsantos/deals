import type { PublishedDeal } from "../types";
import {
  getFreshnessSummary,
  getSourceLabel,
  getSavingsPercentValue,
  getPriceTrustSummary,
  isGreatDeal,
  isLowestIn90Days,
} from "../lib/dealSignals";
import { PriceSparkline } from "./PriceSparkline";

const CATEGORY_COLORS: Record<string, string> = {
  Electronics: "#60a5fa",
  Tech: "#60a5fa",
  Home: "#fb923c",
  Sports: "#4ade80",
  Beauty: "#f472b6",
  Health: "#34d399",
  Kitchen: "#fdba74",
  Fashion: "#c084fc",
  Books: "#818cf8",
  Toys: "#fbbf24",
  Garden: "#86efac",
  Office: "#94a3b8",
  Lifestyle: "#e879f9",
  Food: "#fcd34d",
  Automotive: "#6ee7b7",
  Baby: "#fda4af",
  Pets: "#a3e635",
  Travel: "#38bdf8",
  Music: "#fb7185",
  Tools: "#a78bfa",
};

function getCategoryColor(category: string | null): string {
  if (!category) return "#52525b";
  return CATEGORY_COLORS[category] ?? "#52525b";
}

export function DealCard({
  deal,
  isSaved,
  isSavePending,
  personalizationLabel,
  onToggleSave,
  onOutboundClick,
  onViewDetails,
}: {
  deal: PublishedDeal;
  isSaved: boolean;
  isSavePending: boolean;
  personalizationLabel?: string | null;
  onToggleSave: () => void;
  onOutboundClick?: () => void;
  onViewDetails: (dealId: string) => void;
}) {
  const { currentPrice, previousPrice } = getPriceTrustSummary(deal);
  const savingsValue = getSavingsPercentValue(deal);
  const isGreat = isGreatDeal(deal);
  const isLowest = isLowestIn90Days(deal);
  const isFresh = getFreshnessSummary(deal) === "Fresh price drop";
  const categoryColor = getCategoryColor(deal.category);
  const source = getSourceLabel(deal.deal_url) ?? "Merchant";

  return (
    <article
      className="d-card"
      role="link"
      tabIndex={0}
      aria-label={`${deal.title} — ${currentPrice}`}
      onClick={() => {
        onOutboundClick?.();
        onViewDetails(deal.id);
      }}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOutboundClick?.();
          onViewDetails(deal.id);
        }
      }}
    >
      <div className="d-card-accent" style={{ background: categoryColor }} />

      <div className="d-card-inner">
        <div className="d-card-top">
          <div className="d-card-badges">
            {isGreat && <span className="d-badge d-badge-fire">🔥 Hot</span>}
            {isLowest && <span className="d-badge d-badge-low">↓ Preço mínimo</span>}
            {isFresh && !isLowest && <span className="d-badge d-badge-fresh">Nova queda</span>}
            {deal.category && !isGreat && !isLowest && !isFresh && (
              <span
                className="d-badge d-badge-cat"
                style={{
                  color: categoryColor,
                  borderColor: `${categoryColor}33`,
                  background: `${categoryColor}11`,
                }}
              >
                {deal.category}
              </span>
            )}
          </div>
          <button
            type="button"
            className={`d-save-btn${isSaved ? " d-save-btn-active" : ""}`}
            aria-label={isSaved ? "Remover dos guardados" : "Guardar deal"}
            aria-pressed={isSaved}
            disabled={isSavePending}
            onClick={(e) => {
              e.stopPropagation();
              onToggleSave();
            }}
          >
            {isSaved ? "♥" : "♡"}
          </button>
        </div>

        <div className="d-card-title">{deal.title}</div>

        {personalizationLabel ? (
          <div className="d-card-why">{personalizationLabel}</div>
        ) : null}

        <div className="d-card-price-block">
          <div className="d-price-row">
            <span className="d-price-current">{currentPrice}</span>
            {savingsValue > 0 && (
              <span className={`d-savings-badge${savingsValue >= 30 ? " d-savings-strong" : ""}`}>
                -{Math.round(savingsValue)}%
              </span>
            )}
          </div>
          {previousPrice && (
            <div className="d-price-was">
              era <s>{previousPrice}</s>
            </div>
          )}
        </div>

        <div className="d-card-data-row">
          <PriceSparkline
            history={deal.score_breakdown.price_history}
            currentPrice={deal.current_price}
          />
          <span className="d-card-source">{source}</span>
        </div>
      </div>
    </article>
  );
}
