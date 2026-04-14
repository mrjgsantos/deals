import type { DealPriceHistory } from "../types";

function buildPoints(history: DealPriceHistory | null, currentPrice: string): number[] {
  const candidates: Array<string | null | undefined> = [
    history?.avg_90d,
    history?.avg_30d,
    currentPrice,
  ];

  const points = candidates
    .filter((p): p is string => p != null && p !== "")
    .map(Number)
    .filter((n) => Number.isFinite(n) && n > 0);

  return points.length >= 2 ? points : [];
}

export function PriceSparkline({
  history,
  currentPrice,
  width = 72,
  height = 28,
}: {
  history: DealPriceHistory | null;
  currentPrice: string;
  width?: number;
  height?: number;
}) {
  const points = buildPoints(history, currentPrice);
  if (points.length < 2) return null;

  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const pad = 3;

  const coords = points.map((p, i) => {
    const x = pad + (i / (points.length - 1)) * (width - pad * 2);
    const y = pad + (1 - (p - min) / range) * (height - pad * 2);
    return [x, y] as [number, number];
  });

  const polylinePoints = coords.map(([x, y]) => `${x},${y}`).join(" ");
  const [lastX, lastY] = coords[coords.length - 1];
  const isDown = points[points.length - 1] < points[0];
  const stroke = isDown ? "#2dd06a" : "#ef4444";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      aria-hidden="true"
      className="price-sparkline"
      style={{ display: "block", flexShrink: 0 }}
    >
      <polyline
        points={polylinePoints}
        fill="none"
        stroke={stroke}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.75"
      />
      <circle cx={lastX} cy={lastY} r="2.5" fill={stroke} opacity="0.9" />
    </svg>
  );
}
