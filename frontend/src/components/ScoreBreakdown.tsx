import type { DealScoreBreakdown } from "../types";
import { formatMoney, toSentenceCase } from "../lib/format";
import { Badge } from "./Badge";

export function ScoreBreakdown({ score, currency }: { score: DealScoreBreakdown; currency: string }) {
  const history = score.price_history;

  return (
    <section className="detail-block">
      <div className="detail-block-title">Score breakdown</div>
      <div className="score-grid">
        <div className="score-card">
          <span className="score-label">Quality</span>
          <strong>{score.quality_score ?? "—"}</strong>
        </div>
        <div className="score-card">
          <span className="score-label">Business</span>
          <strong>{score.business_score ?? "—"}</strong>
        </div>
        <div className="score-card">
          <span className="score-label">Promotable</span>
          <Badge value={score.promotable} tone={score.promotable ? "success" : "warning"} />
        </div>
        <div className="score-card">
          <span className="score-label">Fake discount</span>
          <Badge value={score.fake_discount} tone={score.fake_discount ? "danger" : "success"} />
        </div>
      </div>
      {history ? (
        <div className="history-summary-grid">
          <div className="score-card">
            <span className="score-label">Avg 30d</span>
            <strong>{formatMoney(history.avg_30d, currency)}</strong>
          </div>
          <div className="score-card">
            <span className="score-label">Avg 90d</span>
            <strong>{formatMoney(history.avg_90d, currency)}</strong>
          </div>
          <div className="score-card">
            <span className="score-label">All-time low</span>
            <strong>{formatMoney(history.all_time_min, currency)}</strong>
          </div>
          <div className="score-card">
            <span className="score-label">History observations</span>
            <strong>{history.observation_count_all_time}</strong>
          </div>
        </div>
      ) : null}
      <div className="reason-columns">
        <div>
          <div className="reason-title">Quality reasons</div>
          <ul className="reason-list">
            {score.quality_reasons.length > 0 ? score.quality_reasons.map((reason) => <li key={reason}>{toSentenceCase(reason)}</li>) : <li>No quality reasons provided</li>}
          </ul>
        </div>
        <div>
          <div className="reason-title">Business reasons</div>
          <ul className="reason-list">
            {score.business_reasons.length > 0 ? score.business_reasons.map((reason) => <li key={reason}>{toSentenceCase(reason)}</li>) : <li>No business reasons provided</li>}
          </ul>
        </div>
      </div>
    </section>
  );
}
