# Deal Expiry Job — Design Spec

**Date:** 2026-04-29  
**Status:** Approved

## Problem

`Deal.current_price` is a snapshot taken at scoring time and never updated after publication. If the Amazon price rises significantly after a deal is published, the app shows a price that no longer exists, degrading user trust.

## Goal

Expire published (and approved) deals automatically when the current market price is no longer a real discount relative to historical averages — using the same criterion the scoring pipeline uses to reject deals.

## Expiry Criterion

A deal is expired when:

```
current_price > weighted_baseline
```

Where:

- `current_price` = `aggregation.current_price` (most recent `PriceObservation.sale_price` for the product variant)
- `weighted_baseline` = `avg_30d × 0.6 + avg_90d × 0.4`
  - Falls back to `avg_30d` alone if `avg_90d` is unavailable, and vice-versa
  - If no baseline can be computed (no 30d or 90d history) → **skip**, do not expire

This is identical to the `price_above_historical_average` hard-kill check in `daily_scoring.py`, ensuring expiry is consistent with the scoring system.

## Scope

Deals checked: `status IN (PUBLISHED, APPROVED)` with a non-null `product_variant_id`.  
Deals without `product_variant_id` are skipped (no price history to query).

## Implementation

### `app/pricing/scoring.py`

Extract private `_best_baseline` into a public function:

```python
def compute_weighted_price_baseline(
    avg_30d: Decimal | None,
    avg_90d: Decimal | None,
) -> Decimal | None:
```

Update the existing `_best_baseline` call inside `score_deal_quality` to delegate to this new function.

### `app/jobs/daily_deal_expiry.py`

New job following the same pattern as `daily_auto_publish`:

1. Query all `PUBLISHED` + `APPROVED` deals with `product_variant_id IS NOT NULL`
2. For each deal:
   - Call `aggregate_price_history_for_variant(db, deal.product_variant_id)`
   - Call `compute_weighted_price_baseline(agg.avg_30d, agg.avg_90d)`
   - If `baseline is None` → skip
   - If `agg.current_price > baseline` → set `deal.status = DealStatus.EXPIRED`, log reason
3. Commit per-deal inside `db.begin_nested()` for fault isolation
4. Log summary: `total_checked`, `expired`, `skipped_no_baseline`, `skipped_price_ok`, `failed`

### `app/jobs/run_daily.py`

Add `deal_expiry` step after `auto_publish`:

```
stats_recompute → scoring → auto_publish → deal_expiry → ai_drafts
```

## Files Changed

| File | Change |
|------|--------|
| `app/pricing/scoring.py` | Extract `_best_baseline` → `compute_weighted_price_baseline` (public) |
| `app/jobs/daily_deal_expiry.py` | New job |
| `app/jobs/run_daily.py` | Add `deal_expiry` step |

## Out of Scope

- Frontend "expired" badge (deals with `status=EXPIRED` are already excluded from the published feed by existing queries)
- Re-activating expired deals if the price drops again (separate concern)
- Expiring deals without a `product_variant_id` (no price history available)
