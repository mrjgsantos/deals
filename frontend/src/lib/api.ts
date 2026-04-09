import type { Deal, ReviewDecision, ReviewItem } from "../types";

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    let message = response.statusText;

    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) {
        message = body.detail;
      }
    } catch {
      // Keep the HTTP status text when the response body is not JSON.
    }

    throw new ApiError({
      status: response.status,
      message,
    });
  }

  return (await response.json()) as T;
}

export const api = {
  getPendingReviews() {
    return request<ReviewItem[]>("/api/v1/review/pending");
  },
  getDeals() {
    return request<Deal[]>("/api/v1/deals");
  },
  getDeal(id: string) {
    return request<Deal>(`/api/v1/deals/${id}`);
  },
  approveReview(reviewId: string) {
    return request<ReviewDecision>(`/api/v1/review/${reviewId}/approve`, {
      method: "POST",
    });
  },
  rejectReview(reviewId: string) {
    return request<ReviewDecision>(`/api/v1/review/${reviewId}/reject`, {
      method: "POST",
    });
  },
};
