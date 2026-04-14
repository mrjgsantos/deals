import type { PublishedDeal } from "../types";
import {
  getHistoricalPriceInsight,
  getSourceLabel,
  getSavingsPercentValue,
  getPriceTrustSummary,
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
};

const CATEGORY_BG: Record<string, string> = {
  Electronics: "#E8F0FE",
  Tech: "#E8F0FE",
  Home: "#FFF3E0",
  Sports: "#E8F5E9",
  Beauty: "#FCE4EC",
  Health: "#E0F7FA",
  Kitchen: "#FFF8E1",
  Fashion: "#F3E5F5",
  Books: "#EDE7F6",
  Toys: "#FFFDE7",
  Garden: "#F1F8E9",
  Lifestyle: "#FDE7F9",
};

function getPlaceholderEmoji(category: string | null): string {
  if (!category) return "🏷";
  return CATEGORY_EMOJI[category] ?? "🏷";
}

function getPlaceholderBg(category: string | null): string {
  if (!category) return "#F3F4F6";
  return CATEGORY_BG[category] ?? "#F3F4F6";
}

export function HeroDeal({
  deal,
  onViewDetails,
  onOutboundClick,
}: {
  deal: PublishedDeal;
  onViewDetails: (id: string) => void;
  onOutboundClick?: () => void;
}) {
  const { currentPrice, previousPrice } = getPriceTrustSummary(deal);
  const savingsValue = getSavingsPercentValue(deal);
  const isLowest = isLowestIn90Days(deal);
  const insight = getHistoricalPriceInsight(deal);
  const source = getSourceLabel(deal.deal_url) ?? "Merchant";
  const hasImage = Boolean(deal.image_url);

  return (
    <article
      className="d-hero-card"
      style={!hasImage ? { background: getPlaceholderBg(deal.category) } : undefined}
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
      {/* Image or placeholder */}
      {hasImage ? (
        <img
          className="d-hero-img"
          src={deal.image_url!}
          alt={deal.title}
          loading="eager"
          decoding="async"
        />
      ) : (
        <div className="d-hero-img-placeholder">
          {getPlaceholderEmoji(deal.category)}
        </div>
      )}

      {/* Gradient overlay (only with real image) */}
      {hasImage && <div className="d-hero-overlay" />}

      <div className="d-hero-inner">
        <div className="d-hero-top">
          <div className="d-hero-badges">
            {isLowest && (
              <span className="d-badge d-badge-hero-low">↓ Preço mínimo 90 dias</span>
            )}
            {deal.category && (
              <span
                className="d-badge"
                style={
                  hasImage
                    ? { background: "rgba(255,255,255,0.18)", color: "rgba(255,255,255,0.9)", backdropFilter: "blur(4px)", height: "26px", padding: "0 10px", borderRadius: "8px", fontSize: "12px", fontWeight: "700" }
                    : { background: "rgba(0,0,0,0.07)", color: "#374151", height: "26px", padding: "0 10px", borderRadius: "8px", fontSize: "12px", fontWeight: "700" }
                }
              >
                {deal.category}
              </span>
            )}
          </div>
        </div>

        <div className="d-hero-content">
          <div
            className="d-hero-title"
            style={hasImage ? undefined : { color: "#111111" }}
          >
            {deal.title}
          </div>

          <div className="d-hero-price-area">
            <span
              className="d-hero-price"
              style={hasImage ? undefined : { color: "#111111", textShadow: "none" }}
            >
              {currentPrice}
            </span>
            {savingsValue > 0 && (
              <span
                className="d-hero-savings"
                style={hasImage ? undefined : { background: "rgba(0,0,0,0.08)", color: "#111" }}
              >
                -{Math.round(savingsValue)}%
              </span>
            )}
            {previousPrice && (
              <span
                className="d-hero-was"
                style={hasImage ? undefined : { color: "#666" }}
              >
                {previousPrice}
              </span>
            )}
          </div>

          {insight && (
            <div
              className="d-hero-insight"
              style={hasImage ? undefined : { color: "#555" }}
            >
              {insight}
            </div>
          )}
        </div>

        <div className="d-hero-footer">
          <button
            type="button"
            className="d-hero-cta"
            style={
              hasImage
                ? undefined
                : { background: "#111111", color: "#ffffff" }
            }
            onClick={(e) => {
              e.stopPropagation();
              onOutboundClick?.();
              onViewDetails(deal.id);
            }}
          >
            Ver deal →
          </button>
          <span
            className="d-hero-source"
            style={hasImage ? undefined : { color: "#888" }}
          >
            {source}
          </span>
        </div>
      </div>
    </article>
  );
}
