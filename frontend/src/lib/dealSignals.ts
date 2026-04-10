import type { Deal, DealScoreBreakdown, PublishedDeal } from "../types";
import { normalizePercentValue, toSentenceCase } from "./format";

export type SourceLinkType = "google_redirect" | "direct_merchant" | "unknown";

type ScoredDealLike = {
  score_breakdown: DealScoreBreakdown;
  savings_percent: string | null;
  previous_price: string | null;
};

type HistoryAwareDealLike = ScoredDealLike;

type PublicDealLike = HistoryAwareDealLike & {
  title: string;
  summary: string | null;
  deal_url: string | null;
};

const LOW_CONFIDENCE_REASON_SET = new Set([
  "limited_price_history",
  "limited_discount_support",
  "weak_discount_support",
  "volatile_price_history",
]);
const WEAK_HISTORY_REASON_SET = new Set([
  "limited_price_history",
  "limited_discount_support",
  "weak_discount_support",
]);

function hasReason(deal: HistoryAwareDealLike, reason: string): boolean {
  return deal.score_breakdown.quality_reasons.includes(reason) || deal.score_breakdown.business_reasons.includes(reason);
}

export function getQualityScore(deal: ScoredDealLike): number {
  return deal.score_breakdown.quality_score ?? -1;
}

export function getSavingsPercentValue(deal: ScoredDealLike): number {
  return normalizePercentValue(deal.savings_percent) ?? -1;
}

export function getSourceLinkType(dealUrl: string | null): SourceLinkType {
  if (!dealUrl) {
    return "unknown";
  }

  try {
    const parsed = new URL(dealUrl);
    if (parsed.hostname.includes("google.")) {
      return "google_redirect";
    }
    return "direct_merchant";
  } catch {
    return "unknown";
  }
}

export function getSourceLabel(dealUrl: string | null): string | null {
  if (!dealUrl) {
    return null;
  }

  const linkType = getSourceLinkType(dealUrl);
  if (linkType === "google_redirect") {
    return "Google Shopping";
  }

  try {
    const parsed = new URL(dealUrl);
    return parsed.hostname.replace(/^www\./, "") || null;
  } catch {
    return null;
  }
}

export function isLowConfidenceDeal(deal: HistoryAwareDealLike): boolean {
  const qualityScore = getQualityScore(deal);
  if (qualityScore >= 0 && qualityScore < 70) {
    return true;
  }

  return deal.score_breakdown.quality_reasons.some((reason) => LOW_CONFIDENCE_REASON_SET.has(reason));
}

export function hasWeakHistory(deal: HistoryAwareDealLike): boolean {
  return deal.score_breakdown.quality_reasons.some((reason) => WEAK_HISTORY_REASON_SET.has(reason));
}

export function hasFakeDiscountRisk(deal: HistoryAwareDealLike): boolean {
  return deal.score_breakdown.fake_discount;
}

export function getQualityTone(
  deal: HistoryAwareDealLike,
): "success" | "warning" | "danger" | "neutral" {
  const qualityScore = getQualityScore(deal);
  if (qualityScore >= 75) {
    return "success";
  }
  if (qualityScore >= 65) {
    return "neutral";
  }
  if (qualityScore >= 0) {
    return "warning";
  }
  return "neutral";
}

export function getObservationSummary(deal: HistoryAwareDealLike): string {
  const history = deal.score_breakdown.price_history;
  if (!history) {
    return "History unavailable";
  }

  if (history.observation_count_90d > 0) {
    return `${history.observation_count_90d} obs / 90d`;
  }
  if (history.observation_count_all_time > 0) {
    return `${history.observation_count_all_time} obs total`;
  }
  return "No observations";
}

export function getDecisionReasons(deal: HistoryAwareDealLike, limit = 3): string[] {
  const seen = new Set<string>();
  const reasons: string[] = [];

  for (const reason of [...deal.score_breakdown.quality_reasons, ...deal.score_breakdown.business_reasons]) {
    if (!reason || seen.has(reason)) {
      continue;
    }
    seen.add(reason);
    reasons.push(toSentenceCase(reason));
    if (reasons.length >= limit) {
      break;
    }
  }

  return reasons;
}

export function getHistorySupportSummary(deal: HistoryAwareDealLike): string {
  const history = deal.score_breakdown.price_history;
  if (hasReason(deal, "strong_history_support")) {
    return history
      ? `Strong support (${history.observation_count_90d} obs / 90d)`
      : "Strong 90d support";
  }
  if (hasReason(deal, "adequate_history_support")) {
    return history
      ? `Moderate support (${history.observation_count_90d} obs / 90d)`
      : "Moderate 90d support";
  }
  if (hasReason(deal, "weak_discount_support")) {
    return "Shallow history";
  }
  if (hasReason(deal, "limited_discount_support") || hasReason(deal, "limited_price_history")) {
    return "Limited history";
  }
  return "History not highlighted";
}

export function getVolatilitySummary(deal: HistoryAwareDealLike): string {
  if (hasReason(deal, "stable_price_history")) {
    return "Stable price range";
  }
  if (hasReason(deal, "volatile_price_history")) {
    return "Volatile pricing";
  }
  return "No volatility signal";
}

export function getHistoricalValueSummary(deal: HistoryAwareDealLike): string {
  if (deal.previous_price == null) {
    if (hasReason(deal, "weak_discount_support") || hasReason(deal, "limited_discount_support")) {
      return "No supported savings baseline";
    }
    return "No historical baseline shown";
  }

  const history = deal.score_breakdown.price_history;
  if (history?.avg_30d) {
    return `Savings grounded by recent history (${history.observation_count_30d} obs / 30d)`;
  }
  if (history?.avg_90d) {
    return `Savings grounded by broader history (${history.observation_count_90d} obs / 90d)`;
  }
  return "Savings grounded by historical support";
}

export function getHistoryStrengthTone(
  deal: HistoryAwareDealLike,
): "success" | "warning" | "neutral" {
  if (hasReason(deal, "strong_history_support")) {
    return "success";
  }
  if (
    hasReason(deal, "adequate_history_support") ||
    hasReason(deal, "limited_discount_support") ||
    hasReason(deal, "weak_discount_support") ||
    hasReason(deal, "limited_price_history")
  ) {
    return "warning";
  }
  return "neutral";
}

export function getFreshnessSummary(deal: HistoryAwareDealLike): string {
  if (hasReason(deal, "fresh_price_drop")) {
    return "Fresh price drop";
  }
  if (hasReason(deal, "stale_price")) {
    return "Price has been stale";
  }
  return "Freshness neutral";
}

export function getPublicationReadiness(deal: Deal): {
  label: string;
  tone: "success" | "warning" | "danger" | "neutral";
} {
  if (deal.status === "published") {
    return { label: "Published", tone: "success" };
  }
  if (deal.status === "approved") {
    return { label: "Ready to publish", tone: "success" };
  }
  if (deal.status === "pending_review") {
    return { label: "Needs review", tone: "warning" };
  }
  if (deal.status === "rejected") {
    return { label: "Not publishable", tone: "danger" };
  }
  if (deal.status === "expired") {
    return { label: "Expired", tone: "neutral" };
  }
  return { label: "Internal only", tone: "neutral" };
}

export function getSourceSearchText(deal: PublicDealLike): string {
  return [deal.title, deal.summary, getSourceLabel(deal.deal_url), deal.deal_url]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function getPublishedDealTimestamp(deal: PublishedDeal): string {
  return deal.published_at ?? deal.detected_at;
}
