import type { Deal } from "../types";
import { formatDateTime, formatMoney, formatPercent } from "../lib/format";
import { toOutboundAmazonUrl } from "../lib/outboundLinks";
import { Badge } from "./Badge";
import { ScoreBreakdown } from "./ScoreBreakdown";
import {
  getFreshnessSummary,
  getHistoricalValueSummary,
  getHistorySupportSummary,
  getHistoryStrengthTone,
  getPublicationReadiness,
  getSourceLabel,
  getSourceLinkType,
  getVolatilitySummary,
  isLowConfidenceDeal,
} from "../lib/dealSignals";

export function DealSummary({
  deal,
  compact = false,
}: {
  deal: Deal;
  compact?: boolean;
}) {
  const sourceLabel = getSourceLabel(deal.deal_url);
  const sourceLinkType = getSourceLinkType(deal.deal_url);
  const publicationState = getPublicationReadiness(deal);
  const lowConfidence = isLowConfidenceDeal(deal);
  const historySupportSummary = getHistorySupportSummary(deal);
  const historyStrengthTone = getHistoryStrengthTone(deal);
  const historyValueSummary = getHistoricalValueSummary(deal);
  const outboundDealUrl = toOutboundAmazonUrl(deal.deal_url);

  return (
    <div className={compact ? "deal-summary deal-summary-compact" : "deal-summary"}>
      <div className="deal-header">
        <div>
          <div className="eyebrow">Deal</div>
          <h3>{deal.title}</h3>
        </div>
        <div className="badge-cluster">
          <Badge value={deal.status} />
          <Badge value={publicationState.label} tone={publicationState.tone} />
        </div>
      </div>

      <div className="metric-row">
        <div className="metric">
          <span>Current</span>
          <strong>{formatMoney(deal.current_price, deal.currency)}</strong>
        </div>
        <div className="metric">
          <span>Previous baseline</span>
          <strong>{formatMoney(deal.previous_price, deal.currency)}</strong>
        </div>
        <div className="metric">
          <span>Savings</span>
          <strong>{formatMoney(deal.savings_amount, deal.currency)}</strong>
        </div>
        <div className="metric">
          <span>Discount</span>
          <strong>{formatPercent(deal.savings_percent)}</strong>
        </div>
      </div>
      <div className="metric-note-row">
        <Badge value={historySupportSummary} tone={historyStrengthTone} />
        <span className="muted">{historyValueSummary}</span>
      </div>

      {!compact ? (
        <>
          <section className="signal-strip">
            {lowConfidence ? <Badge value="possible low confidence" tone="warning" /> : null}
            {deal.score_breakdown.fake_discount ? <Badge value="fake discount risk" tone="danger" /> : null}
            {sourceLinkType === "google_redirect" ? <Badge value="google redirect link" tone="warning" /> : null}
            {deal.score_breakdown.promotable ? <Badge value="promotable" tone="success" /> : <Badge value="needs caution" tone="warning" />}
          </section>

          <div className="detail-grid">
            <div className="detail-block">
              <div className="detail-block-title">Context</div>
              <dl className="kv-list">
                <div>
                  <dt>Detected</dt>
                  <dd>{formatDateTime(deal.detected_at)}</dd>
                </div>
                <div>
                  <dt>Source / Merchant</dt>
                  <dd>{sourceLabel ?? "—"}</dd>
                </div>
                <div>
                  <dt>Link type</dt>
                  <dd>{sourceLinkType.replace("_", " ")}</dd>
                </div>
                <div>
                  <dt>Publication</dt>
                  <dd>{publicationState.label}</dd>
                </div>
              </dl>
            </div>

            <div className="detail-block">
              <div className="detail-block-title">Summary</div>
              <p className="summary-copy">{deal.summary ?? "No summary provided."}</p>
              <div className="external-link-row">
                {outboundDealUrl ? (
                  <a href={outboundDealUrl} target="_blank" rel="noreferrer">
                    Open source deal
                  </a>
                ) : (
                  <span className="muted">No source URL</span>
                )}
              </div>
            </div>
          </div>

          <section className="detail-grid">
            <div className="detail-block detail-panel">
              <div className="detail-block-title">Decision context</div>
              <dl className="kv-list">
                <div>
                  <dt>History support</dt>
                  <dd>{historySupportSummary}</dd>
                </div>
                <div>
                  <dt>Savings baseline</dt>
                  <dd>{historyValueSummary}</dd>
                </div>
                <div>
                  <dt>Price behavior</dt>
                  <dd>{getVolatilitySummary(deal)}</dd>
                </div>
                <div>
                  <dt>Freshness</dt>
                  <dd>{getFreshnessSummary(deal)}</dd>
                </div>
                <div>
                  <dt>Confidence</dt>
                  <dd>{lowConfidence ? "Needs operator judgement" : "No low-confidence flag"}</dd>
                </div>
              </dl>
            </div>

            <div className="detail-block detail-panel">
              <div className="detail-block-title">Operational IDs</div>
              <dl className="kv-list">
                <div>
                  <dt>Source</dt>
                  <dd>{deal.source_id}</dd>
                </div>
                <div>
                  <dt>Variant</dt>
                  <dd>{deal.product_variant_id ?? "—"}</dd>
                </div>
                <div>
                  <dt>Source record</dt>
                  <dd>{deal.product_source_record_id ?? "—"}</dd>
                </div>
              </dl>
            </div>
          </section>

          <ScoreBreakdown score={deal.score_breakdown} currency={deal.currency} />

          {deal.ai_copy_draft ? (
            <section className="detail-block">
              <div className="detail-block-title">AI copy draft</div>
              <dl className="kv-list kv-list-inline">
                <div>
                  <dt>Status</dt>
                  <dd>{deal.ai_copy_draft.status}</dd>
                </div>
                <div>
                  <dt>Generated</dt>
                  <dd>{formatDateTime(deal.ai_copy_draft.generated_at)}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{deal.ai_copy_draft.model_name ?? "—"}</dd>
                </div>
                <div>
                  <dt>Prompt</dt>
                  <dd>{deal.ai_copy_draft.prompt_version ?? "—"}</dd>
                </div>
              </dl>
              <pre className="draft-json">{JSON.stringify(deal.ai_copy_draft.content, null, 2)}</pre>
              {deal.ai_copy_draft.warnings.length > 0 ? (
                <ul className="reason-list">
                  {deal.ai_copy_draft.warnings.map((warning) => (
                    <li key={warning}>{warning}</li>
                  ))}
                </ul>
              ) : null}
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
