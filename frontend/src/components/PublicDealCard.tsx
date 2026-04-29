import type { PublishedDeal } from "../types";
import { formatDateTime } from "../lib/format";
import { toOutboundAmazonUrl } from "../lib/outboundLinks";
import {
  getFreshnessSummary,
  getHistoricalPriceInsight,
  getHistoryStrengthTone,
  getHistorySupportSummary,
  getPriceTrustSummary,
  getPublishedDealTimestamp,
  getSavingsPercentValue,
  getSourceLabel,
  isGreatDeal,
  isLowestIn90Days,
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
  isSaved,
  isSavePending,
  personalizationLabel,
  onToggleSave,
  onOutboundClick = () => {},
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
  const publishedAt = getPublishedDealTimestamp(deal);
  const sourceLabel = getSourceLabel(deal.deal_url);
  const historySupport = getHistorySupportSummary(deal);
  const historyTone = getHistoryStrengthTone(deal);
  const savingsPercent = getSavingsPercentValue(deal);
  const freshnessSummary = getFreshnessSummary(deal);
  const isLimited = freshnessSummary === "Queda recente";
  const isLowData = historySupport === "Histórico escasso" || historySupport === "Histórico limitado";
  const seenTodayCount = getSeenTodayCount(deal.id);
  const historicalInsight = getHistoricalPriceInsight(deal);
  const isGoodDeal = isGreatDeal(deal);
  const isLowestInHistory = isLowestIn90Days(deal);
  const priceTrustSummary = getPriceTrustSummary(deal);
  const outboundDealUrl = toOutboundAmazonUrl(deal.deal_url);

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
          {isGoodDeal ? <Badge value="🔥 Ótimo deal" tone="success" /> : null}
          {isLowestInHistory ? <Badge value="📉 Mínimo em 90 dias" tone="success" /> : null}
          {isLimited ? <Badge value="⚡ Queda recente" tone="warning" /> : null}
          {isLowData ? <Badge value="⚠️ Poucos dados" tone="warning" /> : null}
          {historySupport ? <Badge value={historySupport} tone={historyTone} /> : null}
        </div>
        <div className="public-card-topline-actions">
          <span className="public-meta-text">Publicado {formatDateTime(publishedAt)}</span>
          <button
            type="button"
            className={isSaved ? "save-button save-button-active" : "save-button"}
            aria-label={isSaved ? "Remover dos guardados" : "Guardar deal"}
            aria-pressed={isSaved}
            disabled={isSavePending}
            onClick={(event) => {
              event.stopPropagation();
              onToggleSave();
            }}
          >
            {isSaved ? "♥" : "♡"}
          </button>
        </div>
      </div>

      <div className="public-card-title">{deal.title}</div>
      {personalizationLabel ? <div className="public-card-why">{personalizationLabel}</div> : null}

      <div className="public-price-block">
        {savingsPercent >= 0 ? (
          <div className={isGoodDeal ? "public-savings-badge public-savings-badge-strong" : "public-savings-badge"}>
            -{priceTrustSummary.savingsPercent}
          </div>
        ) : null}
        <div className="public-price-primary">{priceTrustSummary.currentPrice}</div>
        <div className="public-price-secondary">
          {priceTrustSummary.previousPrice ? (
            <span className="public-price-previous">Antes {priceTrustSummary.previousPrice}</span>
          ) : null}
          {priceTrustSummary.savingsPercent ? <span>Poupa {priceTrustSummary.savingsPercent}</span> : null}
        </div>
      </div>

      {historicalInsight ? <div className="public-history-insight">{historicalInsight}</div> : null}

      {(deal.ai_copy_draft?.content?.summary as string | undefined) ?? deal.summary ? (
        <p className="public-card-summary">
          {(deal.ai_copy_draft?.content?.summary as string | undefined) ?? deal.summary}
        </p>
      ) : null}

      <div className="public-card-footer">
        <div className="public-card-source">
          <div>{sourceLabel ?? "Deal publicado"}</div>
          <div className="public-meta-text">Visto {seenTodayCount}x hoje</div>
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
            Ver detalhes
          </button>
          {outboundDealUrl ? (
            <a
              className="public-cta"
              href={outboundDealUrl}
              target="_blank"
              rel="noreferrer"
              onClick={(event) => {
                event.stopPropagation();
                onOutboundClick();
              }}
            >
              Ver na Amazon →
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}
