import { formatMoney } from "../lib/format";
import type { DealPriceHistory } from "../types";

export function PriceBar({
  priceHistory,
  currentPrice,
  currency,
}: {
  priceHistory: DealPriceHistory | null;
  currentPrice: string;
  currency: string;
}) {
  const ph = priceHistory;
  const current = parseFloat(currentPrice);
  if (!ph || Number.isNaN(current)) return null;

  const min = ph.all_time_min ? parseFloat(ph.all_time_min) : null;
  const avg90 = ph.avg_90d ? parseFloat(ph.avg_90d) : null;
  const max90 = ph.max_90d ? parseFloat(ph.max_90d) : null;

  if (min === null && avg90 === null) return null;

  const lo = min ?? current * 0.8;
  const hi = max90 ?? (avg90 ? avg90 * 1.2 : current * 1.2);
  const range = hi - lo;
  if (range <= 0) return null;

  const pos = Math.max(0, Math.min(1, (current - lo) / range));
  const avgPos = avg90 !== null ? Math.max(0, Math.min(1, (avg90 - lo) / range)) : null;

  const isBelowAvg = avg90 !== null && current < avg90 * 0.95;
  const isAboveAvg = avg90 !== null && current > avg90 * 1.05;
  const dotColor = isBelowAvg ? "#1d6b43" : isAboveAvg ? "#9f2f2f" : "#9a5b08";

  return (
    <div className="price-bar-wrap">
      <div className="price-bar-track">
        {avgPos !== null && (
          <div
            className="price-bar-avg-line"
            style={{ left: `${avgPos * 100}%` }}
            title={`90d avg: ${formatMoney(ph.avg_90d, currency)}`}
          />
        )}
        <div className="price-bar-dot" style={{ left: `${pos * 100}%`, background: dotColor }} />
      </div>
      <div className="price-bar-labels">
        {min !== null && <span>{formatMoney(ph.all_time_min, currency)}</span>}
        {avg90 !== null && <span className="price-bar-avg-label">avg 90d {formatMoney(ph.avg_90d, currency)}</span>}
        {max90 !== null && <span>{formatMoney(ph.max_90d, currency)}</span>}
      </div>
    </div>
  );
}
