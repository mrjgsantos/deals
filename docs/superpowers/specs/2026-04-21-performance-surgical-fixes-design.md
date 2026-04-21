# Performance Surgical Fixes — Design Spec

**Date:** 2026-04-21
**Scope:** Frontend performance only. No backend changes. No new dependencies.

## Problem

Two user-facing symptoms: slow initial load and sluggish navigation between feed, "New for you", and "Saved".

Root causes identified in `frontend/src/`:

1. **`getNewDeals` waterfall** (`App.tsx:203`): the effect has `savedDeals.length` and all `preferences.*` fields in its dependency array. On every authenticated load, this causes the effect to fire 2–3 times: once when `authState` becomes `"authenticated"`, again when `savedDeals` resolves, again when `preferences` resolves. Each firing hits the API unnecessarily.

2. **No render memoization**: every App-level state change (save toggle, preference load) re-renders all mounted `DealCard` and `HeroDeal` components because there are no `React.memo` boundaries and no `useCallback` on the handler props passed down from `App.tsx`.

3. **Over-fetching on initial load**: `INITIAL_COUNT = 24` in `PublicDealsFeedPage` fetches more data than needed for the first viewport, increasing time-to-first-content.

4. **Lazy loading above-fold images**: all `DealCard` images use `loading="lazy"`, including the first ~4 that are visible immediately on load, forcing the browser to wait for IntersectionObserver before fetching them.

## Fixes

### Fix 1 — `getNewDeals` dependency array (`App.tsx`)

Remove `savedDeals.length` and all `preferences.*` fields from the `getNewDeals` effect dependency array. The new-deals endpoint is server-side personalized; the frontend does not need to re-fetch when local preference state updates.

**Before:**
```
[authState.status, savedDeals.length, preferences.categories.join("|"), preferences.intent.join("|"), preferences.budget_preference, preferences.has_pets, preferences.has_kids, preferences.is_profile_initialized]
```

**After:**
```
[authState.status]
```

Result: exactly 1 API call to `getNewDeals` per authenticated session instead of 2–3.

### Fix 2 — Memoize `DealCard` and `HeroDeal`

Wrap both components with `React.memo`. This prevents re-rendering cards when unrelated App state changes (e.g., a different deal is saved, preferences load).

Files: `frontend/src/components/DealCard.tsx`, `frontend/src/components/HeroDeal.tsx`.

### Fix 3 — Stabilize handler refs with `useCallback` (`App.tsx`)

Wrap `navigate`, `onToggleSave`, `onOutboundClick`, and `onImpression` with `useCallback` in `App.tsx`. Without stable refs, `React.memo` on child components has no effect because props always appear changed.

Each callback's dependency array should include only the values it closes over that can actually change (e.g., `onToggleSave` closes over `savedDeals` and auth state).

### Fix 4 — Reduce initial fetch count

Change `INITIAL_COUNT` from `24` to `12` in `PublicDealsFeedPage.tsx`. The page size for subsequent pages is already 12, so this makes the first fetch consistent with the rest. First API response is ~50% smaller; skeletons disappear faster.

### Fix 5 — Eager-load above-fold images

In `DealCard`, accept an optional `priority` boolean prop. When `true`, set `loading="eager"` on the image instead of `lazy`. The feed page passes `priority={index < 4}` to the first 4 cards.

This ensures the browser fetches above-fold images immediately rather than waiting for the lazy-load trigger.

## Scope Boundaries

- No backend changes.
- No new npm packages.
- No changes to routing, state architecture, or API contracts.
- No visual/design changes.
- `PublicDealCard` (used in `NewDealsPage` and `SavedDealsPage`) is out of scope for this fix — it is a separate component that may be addressed in a future design-system unification pass.

## Files Touched

- `frontend/src/App.tsx` — fix dep array, add `useCallback`
- `frontend/src/pages/PublicDealsFeedPage.tsx` — reduce `INITIAL_COUNT`, pass `priority` prop
- `frontend/src/components/DealCard.tsx` — add `React.memo`, add `priority` prop
- `frontend/src/components/HeroDeal.tsx` — add `React.memo`

## Success Criteria

- `getNewDeals` API call appears exactly once in network tab on authenticated load (not 2–3 times)
- Navigating to feed after visiting "Saved" shows content immediately (no re-fetch, no spinner)
- No regressions: save/unsave, infinite scroll, category filter, impression tracking all work correctly
