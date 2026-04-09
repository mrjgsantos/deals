from enum import StrEnum


class SourceType(StrEnum):
    WEBSITE = "website"
    AFFILIATE_FEED = "affiliate_feed"
    MERCHANT_API = "merchant_api"
    MARKETPLACE = "marketplace"
    MANUAL = "manual"


class AvailabilityStatus(StrEnum):
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    UNKNOWN = "unknown"


class PriceStatisticWindow(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"


class DealStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    EXPIRED = "expired"
    REJECTED = "rejected"


class ReviewStatus(StrEnum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReviewType(StrEnum):
    MERCHANT_MATCH = "merchant_match"
    PRODUCT_MATCH = "product_match"
    VARIANT_MATCH = "variant_match"
    DEAL_VALIDATION = "deal_validation"
    COPY_REVIEW = "copy_review"


class AICopyType(StrEnum):
    PACKAGE = "package"
    HEADLINE = "headline"
    BODY = "body"
    SHORT_DESCRIPTION = "short_description"
    DISCLAIMER = "disclaimer"


class AICopyDraftStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"
