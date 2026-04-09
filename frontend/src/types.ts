export type DealScoreBreakdown = {
  quality_score: number | null;
  quality_reasons: string[];
  business_score: number | null;
  business_reasons: string[];
  promotable: boolean;
  fake_discount: boolean;
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
  score_breakdown: DealScoreBreakdown;
  ai_copy_draft: AICopyDraft | null;
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

export type ReviewDecision = {
  review_id: string;
  review_status: string;
  deal_id: string;
  deal_status: string;
};
