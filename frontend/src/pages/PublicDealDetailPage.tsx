import { useEffect, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import { Badge } from "../components/Badge";
import { StatusMessage } from "../components/StatusMessage";
import {
  getFreshnessSummary,
  getHistoryStrengthTone,
  getHistorySupportSummary,
  getPublishedDealTimestamp,
  getSourceLabel,
  getVolatilitySummary,
  isLowConfidenceDeal,
} from "../lib/dealSignals";
import { formatDateTime, formatMoney, formatPercent, toSentenceCase } from "../lib/format";
import { toOutboundAmazonUrl } from "../lib/outboundLinks";
import type { PublishedDeal } from "../types";

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Something went wrong while loading this deal.", {
    404: "This published deal could not be found.",
  });
}

export function PublicDealDetailPage({
  dealId,
  navigate,
  isSaved,
  isSavePending,
  onToggleSave,
  onOutboundClick,
}: {
  dealId: string;
  navigate: (path: string) => void;
  isSaved: boolean;
  isSavePending: boolean;
  onToggleSave: (deal: PublishedDeal) => void;
  onOutboundClick: (deal: PublishedDeal) => void;
}) {
  const [deal, setDeal] = useState<PublishedDeal | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadDeal() {
      setIsLoading(true);
      setError(null);

      try {
        const data = await api.getPublishedDeal(dealId);
        setDeal(data);
      } catch (loadError) {
        setError(getErrorMessage(loadError));
      } finally {
        setIsLoading(false);
      }
    }

    void loadDeal();
  }, [dealId]);

  if (isLoading) {
    return (
      <div className="public-shell">
        <StatusMessage tone="info" title="Loading deal" detail="Fetching the latest published detail." />
      </div>
    );
  }

  if (error || !deal) {
    return (
      <div className="public-shell">
        <div className="public-back-row">
          <button type="button" className="secondary-button" onClick={() => navigate("/")}>
            Back to deals
          </button>
        </div>
        <StatusMessage tone="error" title="Could not load deal" detail={error ?? "Published deal not found."} />
      </div>
    );
  }

  const publishedAt = getPublishedDealTimestamp(deal);
  const historySupport = getHistorySupportSummary(deal);
  const historyTone = getHistoryStrengthTone(deal);
  const sourceLabel = getSourceLabel(deal.deal_url);
  const lowConfidence = isLowConfidenceDeal(deal);
  const priceHistory = deal.score_breakdown.price_history;
  const outboundDealUrl = toOutboundAmazonUrl(deal.deal_url);

  return (
    <div className="public-shell">
      <div className="public-back-row">
        <button type="button" className="secondary-button" onClick={() => navigate("/")}>
          Back to deals
        </button>
      </div>

      <article className="public-detail-shell">
        <section className="public-detail-hero">
          <div className="public-detail-meta">
            <Badge value={historySupport} tone={historyTone} />
            {lowConfidence ? <Badge value="Needs caution" tone="warning" /> : <Badge value="History-backed" tone="success" />}
            <span className="public-meta-text">Published {formatDateTime(publishedAt)}</span>
          </div>

          <h1 className="public-detail-title">{deal.title}</h1>

          <p className="public-detail-summary">
            {(deal.ai_copy_draft?.content?.summary as string | undefined)
              ?? deal.summary
              ?? "Published deal with real historical pricing context and a direct path to the merchant."}
          </p>

          <div className="public-detail-actions">
            {outboundDealUrl ? (
              <a
                className="public-cta public-cta-large"
                href={outboundDealUrl}
                target="_blank"
                rel="noreferrer"
                onClick={() => onOutboundClick(deal)}
              >
                Open deal
              </a>
            ) : null}
            <button
              type="button"
              className={isSaved ? "secondary-button save-detail-button save-detail-button-active" : "secondary-button save-detail-button"}
              disabled={isSavePending}
              onClick={() => onToggleSave(deal)}
            >
              {isSaved ? "♥ Saved" : "♡ Save"}
            </button>
            {sourceLabel ? <span className="public-meta-text">{sourceLabel}</span> : null}
          </div>
        </section>

        <section className="public-detail-layout">
          <div className="public-detail-main">
            <div className="public-pricing-panel">
              <div className="public-price-primary public-price-primary-large">
                {formatMoney(deal.current_price, deal.currency)}
              </div>
              <div className="public-pricing-secondary-grid">
                <div className="public-detail-metric">
                  <span>Previous price</span>
                  <strong>{formatMoney(deal.previous_price, deal.currency)}</strong>
                </div>
                <div className="public-detail-metric">
                  <span>Savings</span>
                  <strong>{formatMoney(deal.savings_amount, deal.currency)}</strong>
                </div>
                <div className="public-detail-metric">
                  <span>Discount</span>
                  <strong>{formatPercent(deal.savings_percent)}</strong>
                </div>
              </div>
            </div>

            <section className="public-panel">
              <div className="public-panel-title">Why this deal stands out</div>
              <ul className="public-reason-list">
                {deal.score_breakdown.quality_reasons.length > 0 ? (
                  deal.score_breakdown.quality_reasons.map((reason) => <li key={reason}>{toSentenceCase(reason)}</li>)
                ) : (
                  <li>Published with no extra historical notes.</li>
                )}
              </ul>
            </section>
          </div>

          <aside className="public-detail-sidebar">
            <section className="public-panel">
              <div className="public-panel-title">Confidence</div>
              <div className="public-sidebar-stack">
                <div className="public-detail-kv">
                  <span>History support</span>
                  <strong>{historySupport}</strong>
                </div>
                <div className="public-detail-kv">
                  <span>Freshness</span>
                  <strong>{getFreshnessSummary(deal)}</strong>
                </div>
                <div className="public-detail-kv">
                  <span>Price behavior</span>
                  <strong>{getVolatilitySummary(deal)}</strong>
                </div>
                <div className="public-detail-kv">
                  <span>Quality score</span>
                  <strong>{deal.score_breakdown.quality_score ?? "—"}</strong>
                </div>
              </div>
            </section>

            {priceHistory ? (
              <section className="public-panel">
                <div className="public-panel-title">Historical context</div>
                <div className="public-sidebar-stack">
                  <div className="public-detail-kv">
                    <span>Avg 30d</span>
                    <strong>{formatMoney(priceHistory.avg_30d, deal.currency)}</strong>
                  </div>
                  <div className="public-detail-kv">
                    <span>Avg 90d</span>
                    <strong>{formatMoney(priceHistory.avg_90d, deal.currency)}</strong>
                  </div>
                  <div className="public-detail-kv">
                    <span>All-time low</span>
                    <strong>{formatMoney(priceHistory.all_time_min, deal.currency)}</strong>
                  </div>
                  <div className="public-detail-kv">
                    <span>Observations</span>
                    <strong>{priceHistory.observation_count_all_time}</strong>
                  </div>
                </div>
              </section>
            ) : null}
          </aside>
        </section>
      </article>
    </div>
  );
}
