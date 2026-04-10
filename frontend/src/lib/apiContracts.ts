import type {
  AICopyDraft,
  Deal,
  DealPriceHistory,
  DealScoreBreakdown,
  PublishedDeal,
  ReviewDecision,
  ReviewItem,
  TrackedProductItem,
  TrackedProductsResponse,
  TrackedProductsSchedulerStatus,
  TrackedProductsSummary,
} from "../types";

type ApiRecord = Record<string, unknown>;

export class ApiContractError extends Error {}

function isRecord(value: unknown): value is ApiRecord {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function expectRecord(value: unknown, context: string): ApiRecord {
  if (!isRecord(value)) {
    throw new ApiContractError(`${context} should be an object.`);
  }
  return value;
}

function expectArray(value: unknown, context: string): unknown[] {
  if (!Array.isArray(value)) {
    throw new ApiContractError(`${context} should be an array.`);
  }
  return value;
}

function readRequiredString(record: ApiRecord, field: string, context: string): string {
  const value = record[field];
  if (typeof value !== "string" || value.trim().length === 0) {
    throw new ApiContractError(`${context}.${field} should be a non-empty string.`);
  }
  return value;
}

function readOptionalString(record: ApiRecord, field: string): string | null {
  const value = record[field];
  return typeof value === "string" ? value : null;
}

function readRequiredNumber(record: ApiRecord, field: string, context: string): number {
  const value = record[field];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new ApiContractError(`${context}.${field} should be a number.`);
  }
  return value;
}

function readOptionalNumber(record: ApiRecord, field: string): number | null {
  const value = record[field];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function readNumberWithDefault(record: ApiRecord, field: string, fallback = 0): number {
  return readOptionalNumber(record, field) ?? fallback;
}

function readBooleanWithDefault(record: ApiRecord, field: string, fallback = false): boolean {
  const value = record[field];
  return typeof value === "boolean" ? value : fallback;
}

function readDecimalLike(record: ApiRecord, field: string): string | null {
  const value = record[field];
  if (typeof value === "string") {
    return value;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    return String(value);
  }
  return null;
}

function readStringArray(record: ApiRecord, field: string): string[] {
  const value = record[field];
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter((item): item is string => typeof item === "string");
}

function normalizePriceHistory(value: unknown): DealPriceHistory | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    avg_30d: readDecimalLike(value, "avg_30d"),
    avg_90d: readDecimalLike(value, "avg_90d"),
    min_90d: readDecimalLike(value, "min_90d"),
    max_90d: readDecimalLike(value, "max_90d"),
    all_time_min: readDecimalLike(value, "all_time_min"),
    days_at_current_price: readOptionalNumber(value, "days_at_current_price"),
    observation_count_30d: readNumberWithDefault(value, "observation_count_30d"),
    observation_count_90d: readNumberWithDefault(value, "observation_count_90d"),
    observation_count_all_time: readNumberWithDefault(value, "observation_count_all_time"),
  };
}

export function parsePublishedDeals(value: unknown): PublishedDeal[] {
  return expectArray(value, "published_deals").map((item) => normalizePublishedDeal(item));
}

export function parsePublishedDeal(value: unknown): PublishedDeal {
  return normalizePublishedDeal(value);
}

export function parsePendingReviews(value: unknown): ReviewItem[] {
  return expectArray(value, "pending_reviews").map((item) => normalizeReviewItem(item));
}

export function parseDeals(value: unknown): Deal[] {
  return expectArray(value, "deals").map((item) => normalizeDeal(item));
}

export function parseDeal(value: unknown): Deal {
  return normalizeDeal(value);
}

export function parseReviewDecision(value: unknown): ReviewDecision {
  return normalizeReviewDecision(value);
}

export function parseTrackedProductsResponse(value: unknown): TrackedProductsResponse {
  const record = expectRecord(value, "tracked_products_response");
  const items = Array.isArray(record.items) ? record.items.map((item) => normalizeTrackedProductItem(item)) : [];
  return {
    scheduler: normalizeTrackedProductsSchedulerStatus(record.scheduler),
    summary: normalizeTrackedProductsSummary(record.summary),
    items,
  };
}

function normalizeTrackedProductsSummary(value: unknown): TrackedProductsSummary {
  const record = isRecord(value) ? value : {};
  return {
    total_tracked_products: readNumberWithDefault(record, "total_tracked_products"),
    active_tracked_products: readNumberWithDefault(record, "active_tracked_products"),
    never_attempted: readNumberWithDefault(record, "never_attempted"),
    in_progress: readNumberWithDefault(record, "in_progress"),
    succeeded: readNumberWithDefault(record, "succeeded"),
    failed: readNumberWithDefault(record, "failed"),
    retry_backoff: readNumberWithDefault(record, "retry_backoff"),
    due_now: readNumberWithDefault(record, "due_now"),
  };
}

function normalizeScoreBreakdown(value: unknown): DealScoreBreakdown {
  if (!isRecord(value)) {
    return {
      quality_score: null,
      quality_reasons: [],
      business_score: null,
      business_reasons: [],
      promotable: false,
      fake_discount: false,
      price_history: null,
    };
  }

  return {
    quality_score: readOptionalNumber(value, "quality_score"),
    quality_reasons: readStringArray(value, "quality_reasons"),
    business_score: readOptionalNumber(value, "business_score"),
    business_reasons: readStringArray(value, "business_reasons"),
    promotable: readBooleanWithDefault(value, "promotable"),
    fake_discount: readBooleanWithDefault(value, "fake_discount"),
    price_history: normalizePriceHistory(value.price_history),
  };
}

function normalizeAICopyDraft(value: unknown): AICopyDraft | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: readRequiredString(value, "id", "ai_copy_draft"),
    status: readRequiredString(value, "status", "ai_copy_draft"),
    model_name: readOptionalString(value, "model_name"),
    prompt_version: readOptionalString(value, "prompt_version"),
    generated_at: readRequiredString(value, "generated_at", "ai_copy_draft"),
    content: isRecord(value.content) ? value.content : {},
    warnings: readStringArray(value, "warnings"),
  };
}

function normalizeDeal(value: unknown): Deal {
  const record = expectRecord(value, "deal");
  return {
    id: readRequiredString(record, "id", "deal"),
    title: readRequiredString(record, "title", "deal"),
    status: readRequiredString(record, "status", "deal"),
    currency: readRequiredString(record, "currency", "deal"),
    current_price: readRequiredString(record, "current_price", "deal"),
    previous_price: readDecimalLike(record, "previous_price"),
    savings_amount: readDecimalLike(record, "savings_amount"),
    savings_percent: readDecimalLike(record, "savings_percent"),
    deal_url: readOptionalString(record, "deal_url"),
    summary: readOptionalString(record, "summary"),
    source_id: readRequiredString(record, "source_id", "deal"),
    product_variant_id: readOptionalString(record, "product_variant_id"),
    product_source_record_id: readOptionalString(record, "product_source_record_id"),
    detected_at: readRequiredString(record, "detected_at", "deal"),
    score_breakdown: normalizeScoreBreakdown(record.score_breakdown),
    ai_copy_draft: normalizeAICopyDraft(record.ai_copy_draft),
  };
}

function normalizePublishedDeal(value: unknown): PublishedDeal {
  const record = expectRecord(value, "published_deal");
  return {
    id: readRequiredString(record, "id", "published_deal"),
    title: readRequiredString(record, "title", "published_deal"),
    currency: readRequiredString(record, "currency", "published_deal"),
    current_price: readRequiredString(record, "current_price", "published_deal"),
    previous_price: readDecimalLike(record, "previous_price"),
    savings_amount: readDecimalLike(record, "savings_amount"),
    savings_percent: readDecimalLike(record, "savings_percent"),
    deal_url: readOptionalString(record, "deal_url"),
    summary: readOptionalString(record, "summary"),
    detected_at: readRequiredString(record, "detected_at", "published_deal"),
    published_at: readOptionalString(record, "published_at"),
    score_breakdown: normalizeScoreBreakdown(record.score_breakdown),
    ai_copy_draft: normalizeAICopyDraft(record.ai_copy_draft),
  };
}

function normalizeReviewItem(value: unknown): ReviewItem {
  const record = expectRecord(value, "review_item");
  return {
    id: readRequiredString(record, "id", "review_item"),
    status: readRequiredString(record, "status", "review_item"),
    reason: readRequiredString(record, "reason", "review_item"),
    priority: readRequiredNumber(record, "priority", "review_item"),
    created_at: readRequiredString(record, "created_at", "review_item"),
    resolved_at: readOptionalString(record, "resolved_at"),
    deal: normalizeDeal(record.deal),
  };
}

function normalizeReviewDecision(value: unknown): ReviewDecision {
  const record = expectRecord(value, "review_decision");
  return {
    review_id: readRequiredString(record, "review_id", "review_decision"),
    review_status: readRequiredString(record, "review_status", "review_decision"),
    deal_id: readRequiredString(record, "deal_id", "review_decision"),
    deal_status: readRequiredString(record, "deal_status", "review_decision"),
  };
}

function normalizeTrackedProductsSchedulerStatus(value: unknown): TrackedProductsSchedulerStatus {
  const record = isRecord(value) ? value : {};
  return {
    enabled: readBooleanWithDefault(record, "enabled"),
    is_running: readBooleanWithDefault(record, "is_running"),
    interval_seconds: readOptionalNumber(record, "interval_seconds"),
    last_started_at: readOptionalString(record, "last_started_at"),
    last_completed_at: readOptionalString(record, "last_completed_at"),
    last_status: readOptionalString(record, "last_status") ?? "unknown",
    last_error_reason: readOptionalString(record, "last_error_reason"),
    tracked_asins: readOptionalNumber(record, "tracked_asins"),
    eligible_asins: readOptionalNumber(record, "eligible_asins"),
    fetched_products: readOptionalNumber(record, "fetched_products"),
    accepted: readOptionalNumber(record, "accepted"),
    rejected: readOptionalNumber(record, "rejected"),
    failed_batches: readOptionalNumber(record, "failed_batches"),
    skipped_reason: readOptionalString(record, "skipped_reason"),
  };
}

function normalizeTrackedProductItem(value: unknown): TrackedProductItem {
  const record = expectRecord(value, "tracked_product");
  return {
    id: readRequiredString(record, "id", "tracked_product"),
    asin: readRequiredString(record, "asin", "tracked_product"),
    domain_id: readRequiredNumber(record, "domain_id", "tracked_product"),
    display_name: readOptionalString(record, "display_name"),
    source_slug: readOptionalString(record, "source_slug"),
    source_name: readOptionalString(record, "source_name"),
    source_url: readOptionalString(record, "source_url"),
    is_active: readBooleanWithDefault(record, "is_active"),
    last_refresh_attempt_at: readOptionalString(record, "last_refresh_attempt_at"),
    last_successful_refresh_at: readOptionalString(record, "last_successful_refresh_at"),
    last_failed_refresh_at: readOptionalString(record, "last_failed_refresh_at"),
    refresh_status: readOptionalString(record, "refresh_status") ?? "unknown",
    refresh_failure_reason: readOptionalString(record, "refresh_failure_reason"),
    consecutive_refresh_failures: readNumberWithDefault(record, "consecutive_refresh_failures"),
    next_refresh_earliest_at: readOptionalString(record, "next_refresh_earliest_at"),
    refresh_priority: readOptionalString(record, "refresh_priority") ?? "normal",
    staleness_classification: readOptionalString(record, "staleness_classification") ?? "unknown",
    observation_count_all_time: readNumberWithDefault(record, "observation_count_all_time"),
    linked_deal_count: readNumberWithDefault(record, "linked_deal_count"),
    has_pending_review_deal: readBooleanWithDefault(record, "has_pending_review_deal"),
    has_published_deal: readBooleanWithDefault(record, "has_published_deal"),
  };
}
