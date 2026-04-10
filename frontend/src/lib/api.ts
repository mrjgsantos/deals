import type { Deal, PublishedDeal, ReviewDecision, ReviewItem, TrackedProductsResponse } from "../types";
import {
  ApiContractError,
  parseDeal,
  parseDeals,
  parsePendingReviews,
  parsePublishedDeal,
  parsePublishedDeals,
  parseReviewDecision,
  parseTrackedProductsResponse,
} from "./apiContracts";

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

async function request<T>(path: string, parse: (body: unknown) => T, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
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

  if (!response.ok) {
    const message = extractErrorMessage(body) ?? response.statusText;

    throw new ApiError({
      status: response.status,
      message,
    });
  }

  return parse(body);
}

export const api = {
  getPublishedDeals() {
    return request<PublishedDeal[]>("/api/v1/published-deals", parsePublishedDeals);
  },
  getPublishedDeal(id: string) {
    return request<PublishedDeal>(`/api/v1/published-deals/${id}`, parsePublishedDeal);
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
