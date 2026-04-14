import type {
  AuthToken,
  AuthUser,
  Deal,
  NewDealsResponse,
  PublishedDeal,
  PublishedDealsPage,
  ReviewDecision,
  ReviewItem,
  SavedDealItem,
  TrackedProductsResponse,
  UserPreferences,
} from "../types";
import {
  ApiContractError,
  parseAuthToken,
  parseAuthUser,
  parseDeal,
  parseDeals,
  parseNewDealsResponse,
  parsePendingReviews,
  parsePublishedDeal,
  parsePublishedDealsPage,
  parsePublishedDeals,
  parseReviewDecision,
  parseSavedDealItems,
  parseTrackedProductsResponse,
  parseUserPreferences,
} from "./apiContracts";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");

function buildApiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE_URL}${path}`;
}

const AUTH_TOKEN_KEY = "deals.auth.token";
const AUTH_USER_KEY = "deals.auth.user";
const AUTH_EXPIRED_EVENT = "deals:auth-expired";

type ApiErrorDetails = {
  status: number;
  message: string;
};

export class ApiError extends Error {
  status: number;

  constructor({ status, message }: ApiErrorDetails) {
    super(message);
    this.status = status;
  }
}

type RequestOptions = RequestInit & {
  allowAnonymousFallback?: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function formatValidationMessage(detail: unknown): string | null {
  if (!isRecord(detail)) {
    return null;
  }

  const message = typeof detail.msg === "string" ? detail.msg : null;
  const loc = Array.isArray(detail.loc)
    ? detail.loc.filter((part): part is string | number => typeof part === "string" || typeof part === "number")
    : [];

  if (!message) {
    return null;
  }
  if (loc.length === 0) {
    return message;
  }
  return `${loc.join(".")}: ${message}`;
}

function extractErrorMessage(body: unknown): string | null {
  if (!isRecord(body)) {
    return null;
  }

  if (typeof body.detail === "string" && body.detail.trim().length > 0) {
    return body.detail;
  }

  if (Array.isArray(body.detail)) {
    const messages = body.detail.map((item) => formatValidationMessage(item)).filter((item): item is string => Boolean(item));
    if (messages.length > 0) {
      return messages.join("; ");
    }
  }

  if (isRecord(body.detail)) {
    if (typeof body.detail.message === "string" && body.detail.message.trim().length > 0) {
      return body.detail.message;
    }
    if (typeof body.detail.reason === "string" && body.detail.reason.trim().length > 0) {
      return body.detail.reason;
    }
  }

  return typeof body.message === "string" ? body.message : null;
}

export function getApiErrorMessage(error: unknown, fallback: string, byStatus?: Partial<Record<number, string>>): string {
  if (error instanceof ApiError) {
    return byStatus?.[error.status] ?? `Request failed: ${error.message}`;
  }
  if (error instanceof ApiContractError) {
    return "The API returned data in an unexpected format.";
  }
  return fallback;
}

function dispatchAuthExpired(): void {
  window.dispatchEvent(new CustomEvent(AUTH_EXPIRED_EVENT));
}

async function fetchJson(path: string, init?: RequestInit, token?: string | null): Promise<{ response: Response; body: unknown }> {
  const response = await fetch(buildApiUrl(path), {
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    body = null;
  }

  return { response, body };
}

async function request<T>(path: string, parse: (body: unknown) => T, init?: RequestOptions): Promise<T> {
  const token = getStoredAuthToken();
  let { response, body } = await fetchJson(path, init, token);

  if (response.status === 401 && token) {
    clearStoredSession();
    dispatchAuthExpired();

    if (init?.allowAnonymousFallback) {
      ({ response, body } = await fetchJson(path, init, null));
    }
  }

  if (!response.ok) {
    const message = extractErrorMessage(body) ?? response.statusText;

    throw new ApiError({
      status: response.status,
      message,
    });
  }

  return parse(body);
}

export function getStoredAuthToken(): string | null {
  return window.localStorage.getItem(AUTH_TOKEN_KEY);
}

export function getStoredAuthUser(): AuthUser | null {
  const raw = window.localStorage.getItem(AUTH_USER_KEY);
  if (!raw) {
    return null;
  }

  try {
    return parseAuthUser(JSON.parse(raw));
  } catch {
    window.localStorage.removeItem(AUTH_USER_KEY);
    return null;
  }
}

export function storeAuthToken(token: string): void {
  window.localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function storeAuthSession(token: string, user: AuthUser): void {
  storeAuthToken(token);
  window.localStorage.setItem(AUTH_USER_KEY, JSON.stringify(user));
}

export function clearStoredSession(): void {
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
}

export function clearAuthToken(): void {
  clearStoredSession();
}

export function subscribeToAuthExpired(listener: () => void): () => void {
  const handler = () => listener();
  window.addEventListener(AUTH_EXPIRED_EVENT, handler);
  return () => window.removeEventListener(AUTH_EXPIRED_EVENT, handler);
}

export const api = {
  register(email: string, password: string) {
    return request<AuthToken>("/api/v1/auth/register", parseAuthToken, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  login(email: string, password: string) {
    return request<AuthToken>("/api/v1/auth/login", parseAuthToken, {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
  },
  googleLogin(idToken: string) {
    return request<AuthToken>("/api/v1/auth/google", parseAuthToken, {
      method: "POST",
      body: JSON.stringify({ id_token: idToken }),
    });
  },
  getCurrentUser() {
    return request<AuthUser>("/api/v1/auth/me", parseAuthUser);
  },
  getPreferences() {
    return request<UserPreferences>("/api/v1/me/preferences", parseUserPreferences);
  },
  savePreferences(preferences: {
    categories: string[];
    budget_preference: "low" | "medium" | "high" | null;
    intent: string[];
    has_pets: boolean;
    has_kids: boolean;
    context_flags?: Record<string, boolean>;
  }) {
    return request<UserPreferences>("/api/v1/me/preferences", parseUserPreferences, {
      method: "POST",
      body: JSON.stringify(preferences),
    });
  },
  getSavedDeals() {
    return request<SavedDealItem[]>("/api/v1/me/saved-deals", parseSavedDealItems);
  },
  getNewDeals() {
    return request<NewDealsResponse>("/api/v1/me/new-deals", parseNewDealsResponse);
  },
  markNewDealsSeen() {
    return request<{ last_seen_at: string }>("/api/v1/me/new-deals/mark-seen", (body) => {
      if (!isRecord(body) || typeof body.last_seen_at !== "string") {
        throw new ApiContractError("new_deals_seen_response should include last_seen_at.");
      }
      return { last_seen_at: body.last_seen_at };
    }, {
      method: "POST",
    });
  },
  getRecommendedDeals() {
    return request<PublishedDeal[]>("/api/v1/me/recommended-deals", parsePublishedDeals);
  },
  saveDeal(id: string) {
    return request<{ deal_id: string; saved: boolean }>(
      `/api/v1/deals/${id}/save`,
      (body) => {
        if (!isRecord(body) || typeof body.deal_id !== "string" || typeof body.saved !== "boolean") {
          throw new ApiContractError("save_deal_response should include deal_id and saved.");
        }
        return { deal_id: body.deal_id, saved: body.saved };
      },
      { method: "POST" },
    );
  },
  unsaveDeal(id: string) {
    return request<{ deal_id: string; saved: boolean }>(
      `/api/v1/deals/${id}/save`,
      (body) => {
        if (!isRecord(body) || typeof body.deal_id !== "string" || typeof body.saved !== "boolean") {
          throw new ApiContractError("unsave_deal_response should include deal_id and saved.");
        }
        return { deal_id: body.deal_id, saved: body.saved };
      },
      { method: "DELETE" },
    );
  },
  async trackDealClick(id: string) {
    return request<{ deal_id: string; clicked: boolean }>(
      `/api/v1/deals/${id}/click`,
      (body) => {
        if (!isRecord(body) || typeof body.deal_id !== "string" || typeof body.clicked !== "boolean") {
          throw new ApiContractError("deal_click_response should include deal_id and clicked.");
        }
        return { deal_id: body.deal_id, clicked: body.clicked };
      },
      { method: "POST" },
    );
  },
  async trackRecommendedDealClick(id: string) {
    await request<{ deal_id: string; clicked: boolean }>(
      `/api/v1/deals/${id}/click?context=recommended`,
      (body) => {
        if (!isRecord(body) || typeof body.deal_id !== "string" || typeof body.clicked !== "boolean") {
          throw new ApiContractError("deal_click_response should include deal_id and clicked.");
        }
        return { deal_id: body.deal_id, clicked: body.clicked };
      },
      { method: "POST" },
    );
  },
  trackDealImpressions(dealIds: string[], context: "feed" | "recommended") {
    return request<{ tracked: number; context: string }>(
      "/api/v1/me/deal-impressions",
      (body) => {
        if (!isRecord(body) || typeof body.tracked !== "number" || typeof body.context !== "string") {
          throw new ApiContractError("deal_impression_response should include tracked and context.");
        }
        return { tracked: body.tracked, context: body.context };
      },
      {
        method: "POST",
        body: JSON.stringify({ deal_ids: dealIds, context }),
      },
    );
  },
  getPublishedDeals() {
    return request<PublishedDeal[]>("/api/v1/published-deals", parsePublishedDeals, { allowAnonymousFallback: true });
  },
  getPublishedDealsPage(cursor: string | null = null, limit = 12) {
    const params = new URLSearchParams({ limit: String(limit) });
    if (cursor) {
      params.set("cursor", cursor);
    }
    return request<PublishedDealsPage>(`/api/v1/published-deals/page?${params.toString()}`, parsePublishedDealsPage, {
      allowAnonymousFallback: true,
    });
  },
  getPublishedDeal(id: string) {
    return request<PublishedDeal>(`/api/v1/published-deals/${id}`, parsePublishedDeal, { allowAnonymousFallback: true });
  },
  getPendingReviews() {
    return request<ReviewItem[]>("/api/v1/review/pending", parsePendingReviews);
  },
  getDeals() {
    return request<Deal[]>("/api/v1/deals", parseDeals);
  },
  getDeal(id: string) {
    return request<Deal>(`/api/v1/deals/${id}`, parseDeal);
  },
  getTrackedProducts(limit = 200) {
    return request<TrackedProductsResponse>(`/api/v1/metrics/tracked-products?limit=${limit}`, parseTrackedProductsResponse);
  },
  approveReview(reviewId: string) {
    return request<ReviewDecision>(`/api/v1/review/${reviewId}/approve`, parseReviewDecision, {
      method: "POST",
    });
  },
  rejectReview(reviewId: string) {
    return request<ReviewDecision>(`/api/v1/review/${reviewId}/reject`, parseReviewDecision, {
      method: "POST",
    });
  },
};
