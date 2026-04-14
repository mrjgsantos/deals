import type {
  AICopyDraft,
  AuthToken,
  AuthUser,
  Deal,
  DealsListItem,
  DealsListPage,
  NewDealsResponse,
  DealPriceHistory,
  DealScoreBreakdown,
  PublishedDeal,
  PublishedDealsPage,
  ReviewDecision,
  ReviewItem,
  ReviewQueueItem,
  ReviewQueuePage,
  SavedDealItem,
  TrackedProductItem,
  TrackedProductsResponse,
  TrackedProductsSchedulerStatus,
  TrackedProductsSummary,
  UserPreferences,
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

function readRecordOfNumbers(record: ApiRecord, field: string): Record<string, number> {
  const value = record[field];
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, item]) =>
      typeof item === "number" && Number.isFinite(item) ? [[key, item]] : []
    ),
  );
}

function readRecordOfBooleans(record: ApiRecord, field: string): Record<string, boolean> {
  const value = record[field];
  if (!isRecord(value)) {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value).flatMap(([key, item]) => (typeof item === "boolean" ? [[key, item]] : [])),
  );
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

function readRequiredDecimalLike(record: ApiRecord, field: string, context: string): string {
  const value = readDecimalLike(record, field);
  if (value == null) {
    throw new ApiContractError(`${context}.${field} should be a decimal-like string or number.`);
  }
  return value;
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

export function parsePublishedDealsPage(value: unknown): PublishedDealsPage {
  const record = expectRecord(value, "published_deals_page");
  return {
    items: Array.isArray(record.items) ? record.items.map((item) => normalizePublishedDeal(item)) : [],
    next_cursor: readOptionalString(record, "next_cursor"),
    has_more: readBooleanWithDefault(record, "has_more"),
  };
}

export function parsePendingReviews(value: unknown): ReviewItem[] {
  return expectArray(value, "pending_reviews").map((item) => normalizeReviewItem(item));
}

export function parseReviewQueuePage(value: unknown): ReviewQueuePage {
  const record = expectRecord(value, "review_queue_page");
  return {
    items: Array.isArray(record.items) ? record.items.map((item) => normalizeReviewQueueItem(item)) : [],
    total: readNumberWithDefault(record, "total"),
    has_more: readBooleanWithDefault(record, "has_more"),
  };
}

function normalizeReviewQueueItem(value: unknown): ReviewQueueItem {
  const record = expectRecord(value, "review_queue_item");
  return {
    id: readRequiredString(record, "id", "review_queue_item"),
    priority: readRequiredNumber(record, "priority", "review_queue_item"),
    created_at: readRequiredString(record, "created_at", "review_queue_item"),
    deal_id: readRequiredString(record, "deal_id", "review_queue_item"),
    title: readRequiredString(record, "title", "review_queue_item"),
    currency: readRequiredString(record, "currency", "review_queue_item"),
    current_price: readRequiredDecimalLike(record, "current_price", "review_queue_item"),
    previous_price: readDecimalLike(record, "previous_price"),
    savings_amount: readDecimalLike(record, "savings_amount"),
    savings_percent: readDecimalLike(record, "savings_percent"),
    deal_url: readOptionalString(record, "deal_url"),
    source_id: readRequiredString(record, "source_id", "review_queue_item"),
    source_category: readOptionalString(record, "source_category"),
    image_url: readOptionalString(record, "image_url"),
    quality_score: readOptionalNumber(record, "quality_score"),
    business_score: readOptionalNumber(record, "business_score"),
    promotable: readBooleanWithDefault(record, "promotable"),
    fake_discount: readBooleanWithDefault(record, "fake_discount"),
    confidence_level: readOptionalString(record, "confidence_level"),
    quality_reasons: readStringArray(record, "quality_reasons"),
    price_history: normalizePriceHistory(record.price_history),
    asin: readOptionalString(record, "asin"),
  };
}

export function parseDealsListPage(value: unknown): DealsListPage {
  const record = expectRecord(value, "deals_list_page");
  return {
    items: Array.isArray(record.items) ? record.items.map((item) => normalizeDealsListItem(item)) : [],
    total: readNumberWithDefault(record, "total"),
    has_more: readBooleanWithDefault(record, "has_more"),
  };
}

function normalizeDealsListItem(value: unknown): DealsListItem {
  const record = expectRecord(value, "deals_list_item");
  return {
    id: readRequiredString(record, "id", "deals_list_item"),
    title: readRequiredString(record, "title", "deals_list_item"),
    status: readRequiredString(record, "status", "deals_list_item"),
    currency: readRequiredString(record, "currency", "deals_list_item"),
    current_price: readRequiredDecimalLike(record, "current_price", "deals_list_item"),
    previous_price: readDecimalLike(record, "previous_price"),
    savings_amount: readDecimalLike(record, "savings_amount"),
    savings_percent: readDecimalLike(record, "savings_percent"),
    deal_url: readOptionalString(record, "deal_url"),
    detected_at: readRequiredString(record, "detected_at", "deals_list_item"),
    source_id: readRequiredString(record, "source_id", "deals_list_item"),
    source_category: readOptionalString(record, "source_category"),
    image_url: readOptionalString(record, "image_url"),
    quality_score: readOptionalNumber(record, "quality_score"),
    business_score: readOptionalNumber(record, "business_score"),
    promotable: readBooleanWithDefault(record, "promotable"),
    fake_discount: readBooleanWithDefault(record, "fake_discount"),
    confidence_level: readOptionalString(record, "confidence_level"),
    quality_reasons: readStringArray(record, "quality_reasons"),
    price_history: normalizePriceHistory(record.price_history),
    asin: readOptionalString(record, "asin"),
  };
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

export function parseAuthUser(value: unknown): AuthUser {
  return normalizeAuthUser(value);
}

export function parseAuthToken(value: unknown): AuthToken {
  const record = expectRecord(value, "auth_token");
  return {
    access_token: readRequiredString(record, "access_token", "auth_token"),
    token_type: readRequiredString(record, "token_type", "auth_token"),
    user: normalizeAuthUser(record.user),
    is_new_user: readBooleanWithDefault(record, "is_new_user"),
  };
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

export function parseSavedDealItems(value: unknown): SavedDealItem[] {
  return expectArray(value, "saved_deals").map((item) => normalizeSavedDealItem(item));
}

export function parseUserPreferences(value: unknown): UserPreferences {
  const record = expectRecord(value, "user_preferences");
  return {
    categories: readStringArray(record, "categories"),
    budget_preference: ((): "low" | "medium" | "high" | null => {
      const value = readOptionalString(record, "budget_preference");
      return value === "low" || value === "medium" || value === "high" ? value : null;
    })(),
    intent: readStringArray(record, "intent"),
    has_pets: readBooleanWithDefault(record, "has_pets"),
    has_kids: readBooleanWithDefault(record, "has_kids"),
    context_flags: readRecordOfBooleans(record, "context_flags"),
    category_affinity: readRecordOfNumbers(record, "category_affinity"),
    saved_count_by_category: readRecordOfNumbers(record, "saved_count_by_category"),
    clicked_count_by_category: readRecordOfNumbers(record, "clicked_count_by_category"),
    negative_affinity: readRecordOfNumbers(record, "negative_affinity"),
    is_profile_initialized: readBooleanWithDefault(record, "is_profile_initialized"),
  };
}

export function parseNewDealsResponse(value: unknown): NewDealsResponse {
  const record = expectRecord(value, "new_deals");
  return {
    new_count: readNumberWithDefault(record, "new_count"),
    fallback_used: readBooleanWithDefault(record, "fallback_used"),
    last_seen_at: readOptionalString(record, "last_seen_at"),
    deals: Array.isArray(record.deals) ? record.deals.map((item) => normalizePublishedDeal(item)) : [],
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
    current_price: readRequiredDecimalLike(record, "current_price", "deal"),
    previous_price: readDecimalLike(record, "previous_price"),
    savings_amount: readDecimalLike(record, "savings_amount"),
    savings_percent: readDecimalLike(record, "savings_percent"),
    deal_url: readOptionalString(record, "deal_url"),
    summary: readOptionalString(record, "summary"),
    source_id: readRequiredString(record, "source_id", "deal"),
    product_variant_id: readOptionalString(record, "product_variant_id"),
    product_source_record_id: readOptionalString(record, "product_source_record_id"),
    detected_at: readRequiredString(record, "detected_at", "deal"),
    published_at: readOptionalString(record, "published_at"),
    category: readOptionalString(record, "category"),
    subcategories: readStringArray(record, "subcategories"),
    personalization_score: readOptionalNumber(record, "personalization_score"),
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
    current_price: readRequiredDecimalLike(record, "current_price", "published_deal"),
    previous_price: readDecimalLike(record, "previous_price"),
    savings_amount: readDecimalLike(record, "savings_amount"),
    savings_percent: readDecimalLike(record, "savings_percent"),
    deal_url: readOptionalString(record, "deal_url"),
    summary: readOptionalString(record, "summary"),
    detected_at: readRequiredString(record, "detected_at", "published_deal"),
    published_at: readOptionalString(record, "published_at"),
    category: readOptionalString(record, "category"),
    subcategories: readStringArray(record, "subcategories"),
    personalization_score: readOptionalNumber(record, "personalization_score"),
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

function normalizeAuthUser(value: unknown): AuthUser {
  const record = expectRecord(value, "auth_user");
  return {
    id: readRequiredString(record, "id", "auth_user"),
    email: readRequiredString(record, "email", "auth_user"),
    display_name: readOptionalString(record, "display_name"),
    avatar_url: readOptionalString(record, "avatar_url"),
    created_at: readRequiredString(record, "created_at", "auth_user"),
  };
}

function normalizeSavedDealItem(value: unknown): SavedDealItem {
  const record = expectRecord(value, "saved_deal_item");
  return {
    saved_at: readRequiredString(record, "saved_at", "saved_deal_item"),
    deal: normalizePublishedDeal(record.deal),
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
