import { useEffect, useState } from "react";

import { api, getApiErrorMessage } from "../lib/api";
import { Badge } from "../components/Badge";
import { PriceSparkline } from "../components/PriceSparkline";
import { StatusMessage } from "../components/StatusMessage";
import {
  getFreshnessSummary,
  getHistoryStrengthTone,
  getHistorySupportSummary,
  getPublishedDealTimestamp,
  getSourceLabel,
  getUserRelevantReasons,
  getVolatilitySummary,
  isLowConfidenceDeal,
} from "../lib/dealSignals";
import { formatDateTime, formatMoney, formatPercent } from "../lib/format";
import { toOutboundAmazonUrl } from "../lib/outboundLinks";
import type { PublishedDeal } from "../types";

function getErrorMessage(error: unknown): string {
  return getApiErrorMessage(error, "Ocorreu um erro ao carregar este deal.", {
    404: "Este deal não foi encontrado.",
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
        <StatusMessage tone="info" title="A carregar deal" detail="A obter os detalhes mais recentes." />
      </div>
    );
  }

  if (error || !deal) {
    return (
      <div className="public-shell">
        <div className="public-back-row">
          <button type="button" className="secondary-button" onClick={() => navigate("/")}>
            ← Voltar
          </button>
        </div>
        <StatusMessage tone="error" title="Não foi possível carregar o deal" detail={error ?? "Deal não encontrado."} />
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
  const freshness = getFreshnessSummary(deal);
  const volatility = getVolatilitySummary(deal);
  const userReasons = getUserRelevantReasons(deal);
  const daysAtPrice = priceHistory?.days_at_current_price;
  const aiSummary = (deal.ai_copy_draft?.content?.summary as string | undefined) ?? deal.summary;

  return (
    <div className="public-shell">
      <div className="public-back-row">
        <button type="button" className="secondary-button" onClick={() => navigate("/")}>
          ← Voltar
        </button>
      </div>

      <article className="public-detail-shell">
        <section className="public-detail-hero">
          <div className="public-detail-meta">
            {historySupport ? <Badge value={historySupport} tone={historyTone} /> : null}
            {lowConfidence
              ? <Badge value="Usar com cautela" tone="warning" />
              : <Badge value="Suportado por histórico" tone="success" />}
            <span className="public-meta-text">Publicado {formatDateTime(publishedAt)}</span>
          </div>

          <h1 className="public-detail-title">{(deal.ai_copy_draft?.content?.title_pt as string | undefined) ?? deal.title}</h1>

          {aiSummary ? (
            <p className="public-detail-summary">{aiSummary}</p>
          ) : null}

          <div className="public-detail-actions">
            {outboundDealUrl ? (
              <a
                className="public-cta public-cta-large"
                href={outboundDealUrl}
                target="_blank"
                rel="noreferrer"
                onClick={() => onOutboundClick(deal)}
              >
                Ver deal
              </a>
            ) : null}
            <button
              type="button"
              className={isSaved ? "secondary-button save-detail-button save-detail-button-active" : "secondary-button save-detail-button"}
              disabled={isSavePending}
              onClick={() => onToggleSave(deal)}
            >
              {isSaved ? "♥ Guardado" : "♡ Guardar"}
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

              {daysAtPrice != null && daysAtPrice <= 7 ? (
                <div className="public-price-urgency">
                  {daysAtPrice <= 1
                    ? "⚡ Queda de preço de hoje"
                    : daysAtPrice <= 3
                    ? `⚡ Preço a este nível há ${daysAtPrice} dias`
                    : `Preço a este nível há ${daysAtPrice} dias`}
                </div>
              ) : null}

              <div className="public-pricing-secondary-grid">
                <div className="public-detail-metric">
                  <span>Preço anterior</span>
                  <strong>{formatMoney(deal.previous_price, deal.currency)}</strong>
                </div>
                <div className="public-detail-metric">
                  <span>Poupança</span>
                  <strong>{formatMoney(deal.savings_amount, deal.currency)}</strong>
                </div>
                <div className="public-detail-metric">
                  <span>Desconto</span>
                  <strong>{formatPercent(deal.savings_percent)}</strong>
                </div>
              </div>

              {priceHistory ? (
                <div className="public-sparkline-row">
                  <PriceSparkline
                    history={priceHistory}
                    currentPrice={deal.current_price}
                    width={120}
                    height={36}
                  />
                  <div className="public-sparkline-labels">
                    {priceHistory.avg_30d ? (
                      <span>Média 30d: {formatMoney(priceHistory.avg_30d, deal.currency)}</span>
                    ) : null}
                    {priceHistory.all_time_min ? (
                      <span>Mínimo histórico: {formatMoney(priceHistory.all_time_min, deal.currency)}</span>
                    ) : null}
                  </div>
                </div>
              ) : null}
            </div>

            {userReasons.length > 0 ? (
              <section className="public-panel">
                <div className="public-panel-title">Porque se destaca</div>
                <div className="public-reason-chips">
                  {userReasons.map((reason) => (
                    <span key={reason} className="public-reason-chip">{reason}</span>
                  ))}
                </div>
              </section>
            ) : null}
          </div>

          <aside className="public-detail-sidebar">
            <section className="public-panel">
              <div className="public-panel-title">Contexto de preço</div>
              <div className="public-sidebar-stack">
                {historySupport ? (
                  <div className="public-detail-kv">
                    <span>Suporte histórico</span>
                    <strong>{historySupport}</strong>
                  </div>
                ) : null}
                {freshness ? (
                  <div className="public-detail-kv">
                    <span>Frescura</span>
                    <strong>{freshness}</strong>
                  </div>
                ) : null}
                {volatility ? (
                  <div className="public-detail-kv">
                    <span>Comportamento</span>
                    <strong>{volatility}</strong>
                  </div>
                ) : null}
              </div>
            </section>

            {priceHistory ? (
              <section className="public-panel">
                <div className="public-panel-title">Histórico de preços</div>
                <div className="public-sidebar-stack">
                  {priceHistory.avg_30d ? (
                    <div className="public-detail-kv">
                      <span>Média 30d</span>
                      <strong>{formatMoney(priceHistory.avg_30d, deal.currency)}</strong>
                    </div>
                  ) : null}
                  {priceHistory.avg_90d ? (
                    <div className="public-detail-kv">
                      <span>Média 90d</span>
                      <strong>{formatMoney(priceHistory.avg_90d, deal.currency)}</strong>
                    </div>
                  ) : null}
                  {priceHistory.all_time_min ? (
                    <div className="public-detail-kv">
                      <span>Mínimo histórico</span>
                      <strong>{formatMoney(priceHistory.all_time_min, deal.currency)}</strong>
                    </div>
                  ) : null}
                  <div className="public-detail-kv">
                    <span>Observações</span>
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
