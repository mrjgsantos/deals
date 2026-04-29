import type { Deal, DealScoreBreakdown, PublishedDeal, UserPreferences } from "../types";
import { formatMoney, formatPercent, normalizePercentValue, toSentenceCase } from "./format";

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
      ? `Histórico sólido (${history.observation_count_90d} obs / 90d)`
      : "Histórico sólido";
  }
  if (hasReason(deal, "adequate_history_support")) {
    return history
      ? `Histórico adequado (${history.observation_count_90d} obs / 90d)`
      : "Histórico adequado";
  }
  if (hasReason(deal, "weak_discount_support")) {
    return "Histórico escasso";
  }
  if (hasReason(deal, "limited_discount_support") || hasReason(deal, "limited_price_history")) {
    return "Histórico limitado";
  }
  return null as unknown as string;
}

export function getVolatilitySummary(deal: HistoryAwareDealLike): string | null {
  if (hasReason(deal, "stable_price_history")) {
    return "Preço estável";
  }
  if (hasReason(deal, "volatile_price_history")) {
    return "Preço volátil";
  }
  return null;
}

export function getHistoricalValueSummary(deal: HistoryAwareDealLike): string {
  if (deal.previous_price == null) {
    if (hasReason(deal, "weak_discount_support") || hasReason(deal, "limited_discount_support")) {
      return "Sem baseline suportado";
    }
    return "Sem baseline histórico";
  }

  const history = deal.score_breakdown.price_history;
  if (history?.avg_30d) {
    return `Poupança suportada por histórico recente (${history.observation_count_30d} obs / 30d)`;
  }
  if (history?.avg_90d) {
    return `Poupança suportada por histórico alargado (${history.observation_count_90d} obs / 90d)`;
  }
  return "Poupança suportada por histórico";
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

export function getFreshnessSummary(deal: HistoryAwareDealLike): string | null {
  if (hasReason(deal, "fresh_price_drop")) {
    return "Queda recente";
  }
  if (hasReason(deal, "stale_price")) {
    return "Preço estagnado";
  }
  return null;
}

const REASON_LABEL_PT: Record<string, string> = {
  strong_discount_vs_baseline: "Desconto forte vs média histórica",
  meaningful_discount_vs_baseline: "Desconto real vs média histórica",
  at_all_time_low: "Preço mínimo histórico",
  fresh_price_drop: "Queda de preço recente",
  stable_price_history: "Histórico de preço estável",
  high_absolute_savings: "Poupança absoluta elevada",
  meaningful_absolute_savings: "Poupança significativa",
  strong_history_support: "Histórico sólido",
  adequate_history_support: "Histórico adequado",
  high_demand_category: "Categoria de alta procura",
  recognized_brand: "Marca reconhecida",
};

const USER_RELEVANT_REASONS = new Set(Object.keys(REASON_LABEL_PT));

export function getReasonLabelPt(reason: string): string {
  return REASON_LABEL_PT[reason] ?? reason;
}

export function getUserRelevantReasons(deal: HistoryAwareDealLike): string[] {
  return deal.score_breakdown.quality_reasons
    .filter((r) => USER_RELEVANT_REASONS.has(r))
    .map((r) => REASON_LABEL_PT[r]);
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

export function getHistoricalPriceInsight(deal: PublishedDeal): string | null {
  const history = deal.score_breakdown.price_history;
  const baseline = history?.avg_30d ?? history?.avg_90d;
  if (baseline != null) {
    return `Normalmente ${formatMoney(baseline, deal.currency)}, agora ${formatMoney(deal.current_price, deal.currency)}`;
  }
  if (deal.previous_price != null) {
    return `Anteriormente ${formatMoney(deal.previous_price, deal.currency)}, agora ${formatMoney(deal.current_price, deal.currency)}`;
  }
  return null;
}

export function isGreatDeal(deal: PublishedDeal): boolean {
  return getSavingsPercentValue(deal) > 25;
}

export function isLowestIn90Days(deal: PublishedDeal): boolean {
  const history = deal.score_breakdown.price_history;
  if (!history?.min_90d) {
    return false;
  }
  const currentPrice = Number(deal.current_price);
  const min90d = Number(history.min_90d);
  if (!Number.isFinite(currentPrice) || !Number.isFinite(min90d)) {
    return false;
  }
  return currentPrice <= min90d;
}

export function getPopularitySignal(deal: PublishedDeal): number {
  const history = deal.score_breakdown.price_history;
  if (!history) {
    return 0;
  }
  const obs90d = history.observation_count_90d ?? 0;
  const obsAllTime = history.observation_count_all_time ?? 0;
  return Math.min(obs90d, 60) * 10 + Math.min(obsAllTime, 180);
}

export function getFeedTrustRank(deal: PublishedDeal): number {
  const savingsPercent = Math.max(getSavingsPercentValue(deal), 0);
  const popularity = getPopularitySignal(deal);
  const relevance = Math.max(deal.personalization_score ?? 0, 0);
  return savingsPercent * 1_000_000 + popularity * 1_000 + relevance;
}

export function getPriceTrustSummary(deal: PublishedDeal): {
  currentPrice: string;
  previousPrice: string | null;
  savingsPercent: string | null;
} {
  return {
    currentPrice: formatMoney(deal.current_price, deal.currency),
    previousPrice: deal.previous_price ? formatMoney(deal.previous_price, deal.currency) : null,
    savingsPercent: deal.savings_percent ? formatPercent(deal.savings_percent) : null,
  };
}

export function getFeedPersonalizationSummary(preferences: UserPreferences): string | null {
  if (preferences.categories.length > 0) {
    const preview = preferences.categories.slice(0, 2).join(" e ");
    return `Baseado nos teus interesses em ${preview.toLowerCase()}`;
  }
  if (preferences.has_pets) {
    return "Baseado nas tuas preferências de animais de estimação";
  }
  if (preferences.has_kids) {
    return "Baseado nas categorias de família no teu perfil";
  }
  if (preferences.intent.includes("save_money")) {
    return "Baseado no teu objetivo de encontrar as melhores poupanças";
  }
  return null;
}

export function getPersonalizationReasonLabel(
  deal: PublishedDeal,
  preferences: UserPreferences,
): string | null {
  if (deal.category && preferences.categories.includes(deal.category)) {
    return `Porque gostas de ${deal.category.toLowerCase()}`;
  }
  if (preferences.has_pets && (deal.category === "Lifestyle" || deal.subcategories.includes("pet_care"))) {
    return "Baseado no teu perfil";
  }
  if (preferences.has_kids && (deal.category === "Lifestyle" || deal.subcategories.includes("baby_kids"))) {
    return "Baseado no teu perfil";
  }
  if (preferences.intent.includes("save_money") && getSavingsPercentValue(deal) >= 20) {
    return "Selecionado pelas poupanças";
  }
  if (preferences.budget_preference === "low") {
    const numericPrice = Number.parseFloat(deal.current_price);
    if (Number.isFinite(numericPrice) && numericPrice <= 50) {
      return "Dentro do teu orçamento";
    }
  }
  return null;
}
