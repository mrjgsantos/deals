import type { PublishedDeal } from "../types";
import {
  getHistoricalPriceInsight,
  getSourceLabel,
  getSavingsPercentValue,
  getPriceTrustSummary,
  isLowestIn90Days,
} from "../lib/dealSignals";
import { PriceSparkline } from "./PriceSparkline";

type CategoryKey =
  | "Electronics"
  | "Tech"
  | "Home"
  | "Sports"
  | "Beauty"
  | "Health"
  | "Kitchen"
  | "Fashion"
  | "Books"
  | "Toys"
  | "Garden"
  | "Office"
  | "Lifestyle"
  | "Food"
  | "Pets"
  | "Travel";

const CATEGORY_GRADIENTS: Record<CategoryKey, string> = {
  Electronics: "linear-gradient(150deg, rgba(37,99,235,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Tech: "linear-gradient(150deg, rgba(37,99,235,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Home: "linear-gradient(150deg, rgba(194,65,12,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Sports: "linear-gradient(150deg, rgba(21,128,61,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Beauty: "linear-gradient(150deg, rgba(157,23,77,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Health: "linear-gradient(150deg, rgba(15,118,110,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Kitchen: "linear-gradient(150deg, rgba(180,83,9,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Fashion: "linear-gradient(150deg, rgba(109,40,217,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Books: "linear-gradient(150deg, rgba(67,56,202,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Toys: "linear-gradient(150deg, rgba(161,98,7,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Garden: "linear-gradient(150deg, rgba(20,83,45,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Office: "linear-gradient(150deg, rgba(51,65,85,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Lifestyle: "linear-gradient(150deg, rgba(112,26,117,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Food: "linear-gradient(150deg, rgba(146,64,14,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Pets: "linear-gradient(150deg, rgba(63,98,18,0.22) 0%, rgba(14,12,10,0.96) 70%)",
  Travel: "linear-gradient(150deg, rgba(7,89,133,0.22) 0%, rgba(14,12,10,0.96) 70%)",
};

const DEFAULT_GRADIENT =
  "linear-gradient(150deg, rgba(63,63,70,0.25) 0%, rgba(14,12,10,0.96) 70%)";

function getCategoryGradient(category: string | null): string {
  if (!category) return DEFAULT_GRADIENT;
  return CATEGORY_GRADIENTS[category as CategoryKey] ?? DEFAULT_GRADIENT;
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
  const gradient = getCategoryGradient(deal.category);

  return (
    <article
      className="d-hero-card"
      style={{ background: gradient }}
      role="link"
      tabIndex={0}
      aria-label={`Featured deal: ${deal.title} — ${currentPrice}`}
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
      <div className="d-hero-inner">
        <div className="d-hero-top">
          <div className="d-hero-badges">
            {isLowest && (
              <span className="d-badge d-badge-hero-low">↓ Preço mínimo 90 dias</span>
            )}
            {deal.category && (
              <span className="d-badge d-badge-hero-cat">{deal.category}</span>
            )}
          </div>
        </div>

        <div className="d-hero-content">
          <div className="d-hero-title">{deal.title}</div>

          <div className="d-hero-price-area">
            <span className="d-hero-price">{currentPrice}</span>
            {savingsValue > 0 && (
              <span className="d-hero-savings">-{Math.round(savingsValue)}%</span>
            )}
            {previousPrice && (
              <span className="d-hero-was">{previousPrice}</span>
            )}
          </div>

          {insight && <div className="d-hero-insight">{insight}</div>}

          {deal.score_breakdown.price_history && (
            <div className="d-hero-sparkline-row">
              <PriceSparkline
                history={deal.score_breakdown.price_history}
                currentPrice={deal.current_price}
                width={96}
                height={36}
              />
            </div>
          )}
        </div>

        <div className="d-hero-footer">
          <button
            type="button"
            className="d-hero-cta"
            onClick={(e) => {
              e.stopPropagation();
              onOutboundClick?.();
              onViewDetails(deal.id);
            }}
          >
            Ver deal →
          </button>
          <span className="d-hero-source">{source}</span>
        </div>
      </div>
    </article>
  );
}
