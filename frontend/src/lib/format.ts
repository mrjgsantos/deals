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

  const amount = Number(value);
  if (Number.isNaN(amount)) {
    return value;
  }

  return `${amount.toFixed(0)}%`;
}

export function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function toSentenceCase(value: string): string {
  return value.replaceAll("_", " ");
}
