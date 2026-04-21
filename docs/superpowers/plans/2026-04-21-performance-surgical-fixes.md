# Performance Surgical Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate redundant API calls and unnecessary re-renders to fix slow initial load and sluggish navigation.

**Architecture:** Four targeted changes — fix a waterfall dependency array, memoize card components, stabilize handler references with `useCallback`, and reduce the initial fetch size. No new packages, no routing or state architecture changes.

**Tech Stack:** React 18, TypeScript, Vite. Verification via browser DevTools (Network tab + React DevTools Profiler).

---

## File Map

| File | Change |
|------|--------|
| `frontend/src/App.tsx` | Fix `getNewDeals` dep array; wrap `navigate`, `handleToggleSavedDeal`, `handleDealOutboundClick`, `handleDealImpressions` in `useCallback` |
| `frontend/src/pages/PublicDealsFeedPage.tsx` | `INITIAL_COUNT` 24 → 12; pass `priority` to first 4 cards |
| `frontend/src/components/DealCard.tsx` | Add `priority?: boolean` prop; use `loading="eager"` when `priority` is true; wrap export in `React.memo` |
| `frontend/src/components/HeroDeal.tsx` | Wrap export in `React.memo` |

---

## Task 1: Fix `getNewDeals` waterfall in `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx:236-245`

This is the highest-impact fix. The effect currently re-fires every time `savedDeals` or any preference field changes, causing 2–3 redundant API calls on every authenticated load.

- [ ] **Step 1: Open `frontend/src/App.tsx` and find the `getNewDeals` effect (around line 203)**

The effect starts with:
```typescript
useEffect(() => {
  if (authState.status !== "authenticated") {
    return;
  }
  // ...fetches getNewDeals...
}, [
  authState.status,
  savedDeals.length,
  preferences.categories.join("|"),
  preferences.intent.join("|"),
  preferences.budget_preference,
  preferences.has_pets,
  preferences.has_kids,
  preferences.is_profile_initialized,
]);
```

- [ ] **Step 2: Replace the dependency array with just `authState.status`**

Change the closing bracket of the effect from:
```typescript
  }, [
    authState.status,
    savedDeals.length,
    preferences.categories.join("|"),
    preferences.intent.join("|"),
    preferences.budget_preference,
    preferences.has_pets,
    preferences.has_kids,
    preferences.is_profile_initialized,
  ]);
```

To:
```typescript
  }, [authState.status]);
```

- [ ] **Step 3: Verify in the browser**

Start the frontend dev server:
```bash
cd frontend && npm run dev
```

Open the app while logged in. Open DevTools → Network tab → filter by `new`. Reload the page. Confirm `getNewDeals` (or the API path for new deals, e.g. `/api/v1/deals/new`) appears **exactly once** in the Network tab, not 2–3 times.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "perf: fire getNewDeals exactly once per authenticated session

Removed savedDeals.length and preferences.* from the getNewDeals
effect dep array. The endpoint is server-side personalized and does
not need re-fetching when local preference state updates."
```

---

## Task 2: Add `React.memo` to `DealCard`

**Files:**
- Modify: `frontend/src/components/DealCard.tsx`

Wrapping `DealCard` with `React.memo` prevents re-rendering all 12–24 cards in the feed when unrelated App state changes (preferences loading, new-deals badge count, etc.).

- [ ] **Step 1: Open `frontend/src/components/DealCard.tsx`**

Find the export at the bottom of the function definition:
```typescript
export function DealCard({
  // ...
}) {
  // ...
}
```

- [ ] **Step 2: Add `priority` prop and `React.memo`**

Replace the entire component definition and export with the memoized version. Change:

```typescript
export function DealCard({
  deal,
  isSaved,
  isSavePending,
  personalizationLabel,
  onToggleSave,
  onOutboundClick,
  onViewDetails,
}: {
  deal: PublishedDeal;
  isSaved: boolean;
  isSavePending: boolean;
  personalizationLabel?: string | null;
  onToggleSave: () => void;
  onOutboundClick?: () => void;
  onViewDetails: (dealId: string) => void;
}) {
```

To:

```typescript
export const DealCard = React.memo(function DealCard({
  deal,
  isSaved,
  isSavePending,
  personalizationLabel,
  onToggleSave,
  onOutboundClick,
  onViewDetails,
  priority,
}: {
  deal: PublishedDeal;
  isSaved: boolean;
  isSavePending: boolean;
  personalizationLabel?: string | null;
  onToggleSave: () => void;
  onOutboundClick?: () => void;
  onViewDetails: (dealId: string) => void;
  priority?: boolean;
}) {
```

And close it at the very end of the function body by adding `);` after the closing `}`:

```typescript
// before (last line of file):
}

// after:
});
```

- [ ] **Step 3: Add `React` import**

At the top of the file, the import is:
```typescript
import type { PublishedDeal } from "../types";
```

Add `React` to it:
```typescript
import React from "react";
import type { PublishedDeal } from "../types";
```

- [ ] **Step 4: Update the image tag to use the `priority` prop**

Inside the component, find:
```typescript
<img
  className="d-card-img"
  src={deal.image_url}
  alt={deal.title}
  loading="lazy"
  decoding="async"
/>
```

Replace with:
```typescript
<img
  className="d-card-img"
  src={deal.image_url}
  alt={deal.title}
  loading={priority ? "eager" : "lazy"}
  decoding="async"
/>
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/DealCard.tsx
git commit -m "perf: memoize DealCard and add priority image loading prop"
```

---

## Task 3: Add `React.memo` to `HeroDeal`

**Files:**
- Modify: `frontend/src/components/HeroDeal.tsx`

Same reason as `DealCard` — the hero cards re-render on any App state change without memoization.

- [ ] **Step 1: Open `frontend/src/components/HeroDeal.tsx`**

- [ ] **Step 2: Add `React` import**

Change:
```typescript
import type { PublishedDeal } from "../types";
```

To:
```typescript
import React from "react";
import type { PublishedDeal } from "../types";
```

- [ ] **Step 3: Wrap the export in `React.memo`**

Change:
```typescript
export function HeroDeal({
  deal,
  onViewDetails,
  onOutboundClick,
}: {
  deal: PublishedDeal;
  onViewDetails: (id: string) => void;
  onOutboundClick?: () => void;
}) {
```

To:
```typescript
export const HeroDeal = React.memo(function HeroDeal({
  deal,
  onViewDetails,
  onOutboundClick,
}: {
  deal: PublishedDeal;
  onViewDetails: (id: string) => void;
  onOutboundClick?: () => void;
}) {
```

And at the end of the file, change the closing `}` to `});`.

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/HeroDeal.tsx
git commit -m "perf: memoize HeroDeal component"
```

---

## Task 4: Stabilize handler refs with `useCallback` in `App.tsx`

**Files:**
- Modify: `frontend/src/App.tsx`

`React.memo` only prevents re-renders when props are referentially stable. The handlers passed as props from `App.tsx` are plain functions recreated on every render. Wrapping them in `useCallback` gives stable references so memoized children stay still during unrelated state changes.

- [ ] **Step 1: Add `useCallback` to the `React` import in `App.tsx`**

Find the existing React imports at the top of `App.tsx`. They will include `useState`, `useEffect`, `useMemo`, `useRef`. Add `useCallback`:

```typescript
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
```

- [ ] **Step 2: Wrap `navigate` in `useCallback`**

Find the `navigate` function (around line 313):
```typescript
function navigate(path: string) {
  if (path === pathname) {
    return;
  }
  window.history.pushState({}, "", path);
  window.scrollTo({ top: 0, behavior: "auto" });
  setPathname(path);
}
```

Replace with:
```typescript
const navigate = useCallback((path: string) => {
  if (path === pathname) {
    return;
  }
  window.history.pushState({}, "", path);
  window.scrollTo({ top: 0, behavior: "auto" });
  setPathname(path);
}, [pathname]);
```

- [ ] **Step 3: Wrap `handleDealOutboundClick` in `useCallback`**

Find `handleDealOutboundClick` (around line 445):
```typescript
function handleDealOutboundClick(deal: PublishedDeal, context: "feed" | "recommended" = "feed") {
  if (authState.status !== "authenticated") {
    return;
  }
  const tracker = context === "recommended" ? api.trackRecommendedDealClick : api.trackDealClick;
  void tracker(deal.id)
    .then(() => {
      requestFeedRefresh();
    })
    .catch(() => {
      // Personalization click tracking should never block navigation.
    });
}
```

Replace with:
```typescript
const handleDealOutboundClick = useCallback((deal: PublishedDeal, context: "feed" | "recommended" = "feed") => {
  if (authState.status !== "authenticated") {
    return;
  }
  const tracker = context === "recommended" ? api.trackRecommendedDealClick : api.trackDealClick;
  void tracker(deal.id)
    .then(() => {
      requestFeedRefresh();
    })
    .catch(() => {
      // Personalization click tracking should never block navigation.
    });
}, [authState.status]);
```

- [ ] **Step 4: Wrap `handleDealImpressions` in `useCallback`**

Find `handleDealImpressions` (around line 459):
```typescript
function handleDealImpressions(deals: PublishedDeal[], context: "feed" | "recommended") {
  if (authState.status !== "authenticated" || deals.length === 0) {
    return;
  }
  void api.trackDealImpressions(
    deals.map((deal) => deal.id),
    context,
  ).catch(() => {
    // Analytics should never block the user experience.
  });
}
```

Replace with:
```typescript
const handleDealImpressions = useCallback((deals: PublishedDeal[], context: "feed" | "recommended") => {
  if (authState.status !== "authenticated" || deals.length === 0) {
    return;
  }
  void api.trackDealImpressions(
    deals.map((deal) => deal.id),
    context,
  ).catch(() => {
    // Analytics should never block the user experience.
  });
}, [authState.status]);
```

- [ ] **Step 5: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors. If TypeScript complains about `requestFeedRefresh` inside `useCallback` deps, wrap `requestFeedRefresh` in `useCallback` too:
```typescript
const requestFeedRefresh = useCallback(() => {
  setFeedRefreshToken((current) => current + 1);
}, []);
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "perf: stabilize handler refs with useCallback

navigate, handleDealOutboundClick, and handleDealImpressions now have
stable references across renders, so memoized DealCard and HeroDeal
children skip re-renders during unrelated App state changes."
```

---

## Task 5: Reduce initial fetch count and pass `priority` to above-fold cards

**Files:**
- Modify: `frontend/src/pages/PublicDealsFeedPage.tsx`

Halving the initial fetch size reduces time-to-first-content. Passing `priority={true}` to the first 4 cards removes the lazy-load delay for above-fold images.

- [ ] **Step 1: Reduce `INITIAL_COUNT`**

Open `frontend/src/pages/PublicDealsFeedPage.tsx`. Find:
```typescript
const INITIAL_COUNT = 24;
```

Change to:
```typescript
const INITIAL_COUNT = 12;
```

- [ ] **Step 2: Pass `priority` prop to the first 4 cards in the main feed**

Find the main feed grid render (inside the `SectionBlock` at the bottom):
```typescript
{feedDeals.map((deal) => (
  <DealCard
    key={deal.id}
    deal={deal}
    isSaved={savedDealIds.has(deal.id)}
    isSavePending={pendingDealIds.has(deal.id)}
    personalizationLabel={preferences ? getPersonalizationReasonLabel(deal, preferences) : null}
    onToggleSave={() => onToggleSave(deal)}
    onOutboundClick={() => onOutboundClick(deal)}
    onViewDetails={(id) => navigate(`/deals/${id}`)}
  />
))}
```

Change to:
```typescript
{feedDeals.map((deal, index) => (
  <DealCard
    key={deal.id}
    deal={deal}
    isSaved={savedDealIds.has(deal.id)}
    isSavePending={pendingDealIds.has(deal.id)}
    personalizationLabel={preferences ? getPersonalizationReasonLabel(deal, preferences) : null}
    onToggleSave={() => onToggleSave(deal)}
    onOutboundClick={() => onOutboundClick(deal)}
    onViewDetails={(id) => navigate(`/deals/${id}`)}
    priority={index < 4}
  />
))}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Verify in the browser**

Open the app. Open DevTools → Network tab → filter by `deals`. Reload. Confirm the initial deals request fetches 12 items instead of 24. Then scroll down — confirm more deals load as you approach the bottom (infinite scroll still works).

Also open DevTools → Network tab → filter by image type. Confirm the first 4 card images load immediately on page paint, not deferred.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/PublicDealsFeedPage.tsx
git commit -m "perf: reduce initial feed fetch to 12 and eager-load first 4 images"
```

---

## Final Verification

- [ ] **Authenticated load**: Open app while logged in, watch Network tab. Confirm `getNewDeals` fires once. Confirm initial deals request fetches 12 items.
- [ ] **Navigation**: Navigate to "Saved deals", then back to feed. Confirm feed shows content immediately with no spinner.
- [ ] **Save/unsave**: Toggle save on a deal. Confirm save button updates immediately (optimistic). Confirm no console errors.
- [ ] **Infinite scroll**: Scroll to the bottom of the feed. Confirm more deals load automatically.
- [ ] **Category filter**: Click a category. Confirm filtered deals display correctly.
- [ ] **Impression tracking**: No errors in console related to impression tracking.
