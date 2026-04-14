export function formatMoney(value: string | null | undefined, currency: string): string {
  if (value == null) {
    return "—";
  }

  const amount = Number(value);
  if (Number.isNaN(amount)) {
    return value;
  }

  return new Intl.NumberFormat("en-GB", {
    style: "currency",
    currency,
  }).format(amount);
}

export function formatPercent(value: string | null | undefined): string {
  if (value == null) {
    return "—";
  }

  const normalized = normalizePercentValue(value);
  if (normalized == null) {
    return value;
  }

  return `${normalized.toFixed(0)}%`;
}

export function toTimestamp(value: string | null | undefined): number | null {
  if (!value) {
    return null;
  }

  const timestamp = Date.parse(value);
  return Number.isNaN(timestamp) ? null : timestamp;
}

export function formatDateTime(value: string | null | undefined): string {
  const timestamp = toTimestamp(value);
  if (timestamp == null) {
    return "—";
  }

  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

export function toSentenceCase(value: string): string {
  return value.replaceAll("_", " ");
}

export function formatRelativeTime(value: string | null | undefined): string {
  const timestamp = toTimestamp(value);
  if (timestamp == null) return "—";
  const diffMs = Date.now() - timestamp;
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function normalizePercentValue(value: string | number | null | undefined): number | null {
  if (value == null) {
    return null;
  }

  const amount = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(amount)) {
    return null;
  }

  if (Math.abs(amount) <= 1) {
    return amount * 100;
  }

  return amount;
}
