import type { Deal } from "../types";
import { formatDateTime, formatMoney, formatPercent } from "../lib/format";
import { Badge } from "./Badge";
import { ScoreBreakdown } from "./ScoreBreakdown";

export function DealSummary({
  deal,
  compact = false,
}: {
  deal: Deal;
  compact?: boolean;
}) {
  return (
    <div className={compact ? "deal-summary deal-summary-compact" : "deal-summary"}>
      <div className="deal-header">
        <div>
          <div className="eyebrow">Deal</div>
          <h3>{deal.title}</h3>
        </div>
        <Badge value={deal.status} />
      </div>

      <div className="metric-row">
        <div className="metric">
          <span>Current</span>
          <strong>{formatMoney(deal.current_price, deal.currency)}</strong>
        </div>
        <div className="metric">
          <span>Previous</span>
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

      {!compact ? (
        <>
          <div className="detail-grid">
            <div className="detail-block">
              <div className="detail-block-title">Context</div>
              <dl className="kv-list">
                <div>
                  <dt>Detected</dt>
                  <dd>{formatDateTime(deal.detected_at)}</dd>
                </div>
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

            <div className="detail-block">
              <div className="detail-block-title">Summary</div>
              <p className="summary-copy">{deal.summary ?? "No summary provided."}</p>
              <div className="external-link-row">
                {deal.deal_url ? (
                  <a href={deal.deal_url} target="_blank" rel="noreferrer">
                    Open source deal
                  </a>
                ) : (
                  <span className="muted">No source URL</span>
                )}
              </div>
            </div>
          </div>

          <ScoreBreakdown score={deal.score_breakdown} />

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
