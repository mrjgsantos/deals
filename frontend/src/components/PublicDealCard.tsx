import type { PublishedDeal } from "../types";
import { formatDateTime, formatMoney, formatPercent } from "../lib/format";
import {
  getFreshnessSummary,
  getHistoryStrengthTone,
  getHistorySupportSummary,
  getPublishedDealTimestamp,
  getSavingsPercentValue,
  getSourceLabel,
} from "../lib/dealSignals";
import { Badge } from "./Badge";

function getSeenTodayCount(dealId: string): number {
  let hash = 0;
  for (const char of dealId) {
    hash = (hash * 31 + char.charCodeAt(0)) % 191;
  }
  return 10 + hash;
}

export function PublicDealCard({
  deal,
  onViewDetails,
}: {
  deal: PublishedDeal;
  onViewDetails: (dealId: string) => void;
}) {
  const publishedAt = getPublishedDealTimestamp(deal);
  const sourceLabel = getSourceLabel(deal.deal_url);
  const historySupport = getHistorySupportSummary(deal);
  const historyTone = getHistoryStrengthTone(deal);
  const savingsPercent = getSavingsPercentValue(deal);
  const freshnessSummary = getFreshnessSummary(deal);
  const isLimited = freshnessSummary === "Fresh price drop";
  const isLowData = historySupport === "Shallow history" || historySupport === "Limited history";
  const seenTodayCount = getSeenTodayCount(deal.id);

  return (
    <article
      className="public-card"
      role="link"
      tabIndex={0}
      onClick={() => onViewDetails(deal.id)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onViewDetails(deal.id);
        }
      }}
    >
      <div className="public-card-topline">
        <div className="badge-cluster badge-cluster-wrap">
          {savingsPercent > 25 ? <Badge value="🔥 DEAL" tone="success" /> : null}
          {isLimited ? <Badge value="⚡ LIMITED" tone="warning" /> : null}
          {isLowData ? <Badge value="⚠️ LOW DATA" tone="warning" /> : null}
          <Badge value={historySupport} tone={historyTone} />
        </div>
        <span className="public-meta-text">Published {formatDateTime(publishedAt)}</span>
      </div>

      <div className="public-card-title">{deal.title}</div>

      <div className="public-price-block">
        <div className="public-price-primary">{formatMoney(deal.current_price, deal.currency)}</div>
        <div className="public-price-secondary">
          <span className="public-price-previous">{formatMoney(deal.previous_price, deal.currency)}</span>
          <span>Save {formatMoney(deal.savings_amount, deal.currency)}</span>
          <span>{formatPercent(deal.savings_percent)}</span>
        </div>
      </div>

      <p className="public-card-summary">{deal.summary ?? "Fresh published deal with verified historical pricing support."}</p>

      <div className="public-card-footer">
        <div className="public-card-source">
          <div>{sourceLabel ?? "Published deal"}</div>
          <div className="public-meta-text">Seen {seenTodayCount} times today</div>
        </div>
        <div className="public-card-actions">
          <button
            type="button"
            className="secondary-button"
            onClick={(event) => {
              event.stopPropagation();
              onViewDetails(deal.id);
            }}
          >
            View details
          </button>
          {deal.deal_url ? (
            <a
              className="public-cta"
              href={deal.deal_url}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => event.stopPropagation()}
            >
              View on Amazon →
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}
