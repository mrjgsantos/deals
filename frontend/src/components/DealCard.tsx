import type { PublishedDeal } from "../types";
import {
  getFreshnessSummary,
  getSourceLabel,
  getSavingsPercentValue,
  getPriceTrustSummary,
  isGreatDeal,
  isLowestIn90Days,
} from "../lib/dealSignals";

const CATEGORY_EMOJI: Record<string, string> = {
  Electronics: "⚡",
  Tech: "💻",
  Home: "🏠",
  Sports: "🏃",
  Beauty: "✨",
  Health: "💊",
  Kitchen: "🍳",
  Fashion: "👗",
  Books: "📚",
  Toys: "🎮",
  Garden: "🌱",
  Office: "📋",
  Lifestyle: "🌟",
  Food: "🛒",
  Automotive: "🚗",
  Baby: "🍼",
  Pets: "🐾",
  Travel: "✈️",
  Music: "🎵",
  Tools: "🔧",
};

function getPlaceholderEmoji(category: string | null): string {
  if (!category) return "🏷";
  return CATEGORY_EMOJI[category] ?? "🏷";
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
      {/* Image area */}
      <div className="d-card-img-wrap">
        {deal.image_url ? (
          <img
            className="d-card-img"
            src={deal.image_url}
            alt={deal.title}
            loading="lazy"
            decoding="async"
          />
        ) : (
          <div className="d-card-img-placeholder">
            {getPlaceholderEmoji(deal.category)}
          </div>
        )}

        {/* Discount pill over image */}
        {savingsValue > 0 && (
          <div className="d-card-discount-overlay">
            <span className="d-discount-pill">-{Math.round(savingsValue)}%</span>
          </div>
        )}

        {/* Save button over image */}
        <div className="d-card-save-overlay">
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
      </div>

      {/* Card body */}
      <div className="d-card-body">
        <div className="d-card-badges">
          {isGreat && <span className="d-badge d-badge-fire">🔥 Destaque</span>}
          {isLowest && <span className="d-badge d-badge-low">↓ Preço mínimo</span>}
          {isFresh && !isLowest && <span className="d-badge d-badge-fresh">Nova queda</span>}
          {deal.category && !isGreat && !isLowest && !isFresh && (
            <span className="d-badge d-badge-cat">{deal.category}</span>
          )}
        </div>

        <div className="d-card-title">{deal.title}</div>

        {personalizationLabel ? (
          <div className="d-card-why">{personalizationLabel}</div>
        ) : null}

        <div className="d-card-price-block">
          <span className="d-price-current">{currentPrice}</span>
          {previousPrice && (
            <span className="d-price-was"><s>{previousPrice}</s></span>
          )}
        </div>

        <div className="d-card-footer-row">
          <span className="d-card-source">{source}</span>
        </div>
      </div>
    </article>
  );
}
