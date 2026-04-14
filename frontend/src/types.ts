export type DealScoreBreakdown = {
  quality_score: number | null;
  quality_reasons: string[];
  business_score: number | null;
  business_reasons: string[];
  promotable: boolean;
  fake_discount: boolean;
  price_history: DealPriceHistory | null;
};

export type DealPriceHistory = {
  avg_30d: string | null;
  avg_90d: string | null;
  min_90d: string | null;
  max_90d: string | null;
  all_time_min: string | null;
  days_at_current_price: number | null;
  observation_count_30d: number;
  observation_count_90d: number;
  observation_count_all_time: number;
};

export type AICopyDraft = {
  id: string;
  status: string;
  model_name: string | null;
  prompt_version: string | null;
  generated_at: string;
  content: Record<string, unknown>;
  warnings: string[];
};

export type Deal = {
  id: string;
  title: string;
  status: string;
  currency: string;
  current_price: string;
  previous_price: string | null;
  savings_amount: string | null;
  savings_percent: string | null;
  deal_url: string | null;
  summary: string | null;
  source_id: string;
  product_variant_id: string | null;
  product_source_record_id: string | null;
  detected_at: string;
  published_at: string | null;
  category: string | null;
  subcategories: string[];
  personalization_score: number | null;
  score_breakdown: DealScoreBreakdown;
  ai_copy_draft: AICopyDraft | null;
};

export type PublishedDeal = {
  id: string;
  title: string;
  currency: string;
  current_price: string;
  previous_price: string | null;
  savings_amount: string | null;
  savings_percent: string | null;
  deal_url: string | null;
  summary: string | null;
  detected_at: string;
  published_at: string | null;
  category: string | null;
  subcategories: string[];
  personalization_score: number | null;
  score_breakdown: DealScoreBreakdown;
  ai_copy_draft: AICopyDraft | null;
};

export type PublishedDealsPage = {
  items: PublishedDeal[];
  next_cursor: string | null;
  has_more: boolean;
};

export type ReviewItem = {
  id: string;
  status: string;
  reason: string;
  priority: number;
  created_at: string;
  resolved_at: string | null;
  deal: Deal;
};

export type ReviewQueueItem = {
  id: string;
  priority: number;
  created_at: string;
  deal_id: string;
  title: string;
  currency: string;
  current_price: string;
  previous_price: string | null;
  savings_amount: string | null;
  savings_percent: string | null;
  deal_url: string | null;
  source_id: string;
  source_category: string | null;
  image_url: string | null;
  quality_score: number | null;
  business_score: number | null;
  promotable: boolean;
  fake_discount: boolean;
  confidence_level: string | null;
  quality_reasons: string[];
  price_history: DealPriceHistory | null;
  asin: string | null;
};

export type ReviewQueuePage = {
  items: ReviewQueueItem[];
  total: number;
  has_more: boolean;
};

export type ReviewDecision = {
  review_id: string;
  review_status: string;
  deal_id: string;
  deal_status: string;
};

export type AuthUser = {
  id: string;
  email: string;
  display_name: string | null;
  avatar_url: string | null;
  created_at: string;
};

export type AuthToken = {
  access_token: string;
  token_type: string;
  user: AuthUser;
  is_new_user: boolean;
};

export type SavedDealItem = {
  saved_at: string;
  deal: PublishedDeal;
};

export type NewDealsResponse = {
  new_count: number;
  fallback_used: boolean;
  last_seen_at: string | null;
  deals: PublishedDeal[];
};

export type UserPreferences = {
  categories: string[];
  budget_preference: "low" | "medium" | "high" | null;
  intent: string[];
  has_pets: boolean;
  has_kids: boolean;
  context_flags: Record<string, boolean>;
  category_affinity: Record<string, number>;
  saved_count_by_category: Record<string, number>;
  clicked_count_by_category: Record<string, number>;
  negative_affinity: Record<string, number>;
  is_profile_initialized: boolean;
};

export type TrackedProductsSchedulerStatus = {
  enabled: boolean;
  is_running: boolean;
  interval_seconds: number | null;
  last_started_at: string | null;
  last_completed_at: string | null;
  last_status: string;
  last_error_reason: string | null;
  tracked_asins: number | null;
  eligible_asins: number | null;
  fetched_products: number | null;
  accepted: number | null;
  rejected: number | null;
  failed_batches: number | null;
  skipped_reason: string | null;
};

export type TrackedProductsSummary = {
  total_tracked_products: number;
  active_tracked_products: number;
  never_attempted: number;
  in_progress: number;
  succeeded: number;
  failed: number;
  retry_backoff: number;
  due_now: number;
};

export type TrackedProductItem = {
  id: string;
  asin: string;
  domain_id: number;
  display_name: string | null;
  source_slug: string | null;
  source_name: string | null;
  source_url: string | null;
  is_active: boolean;
  last_refresh_attempt_at: string | null;
  last_successful_refresh_at: string | null;
  last_failed_refresh_at: string | null;
  refresh_status: string;
  refresh_failure_reason: string | null;
  consecutive_refresh_failures: number;
  next_refresh_earliest_at: string | null;
  refresh_priority: string;
  staleness_classification: string;
  observation_count_all_time: number;
  linked_deal_count: number;
  has_pending_review_deal: boolean;
  has_published_deal: boolean;
};

export type TrackedProductsResponse = {
  scheduler: TrackedProductsSchedulerStatus;
  summary: TrackedProductsSummary;
  items: TrackedProductItem[];
};
