import type { DealScoreBreakdown } from "../types";
import { Badge } from "./Badge";

export function ScoreBreakdown({ score }: { score: DealScoreBreakdown }) {
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
      <div className="reason-columns">
        <div>
          <div className="reason-title">Quality reasons</div>
          <ul className="reason-list">
            {score.quality_reasons.length > 0 ? score.quality_reasons.map((reason) => <li key={reason}>{reason}</li>) : <li>No quality reasons provided</li>}
          </ul>
        </div>
        <div>
          <div className="reason-title">Business reasons</div>
          <ul className="reason-list">
            {score.business_reasons.length > 0 ? score.business_reasons.map((reason) => <li key={reason}>{reason}</li>) : <li>No business reasons provided</li>}
          </ul>
        </div>
      </div>
    </section>
  );
}
