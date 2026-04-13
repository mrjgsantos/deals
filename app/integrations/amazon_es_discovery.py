from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from html import unescape
import re
from collections.abc import Iterable
from typing import Any
from unicodedata import combining, normalize
from urllib.parse import unquote, urljoin, urlparse

import httpx

from app.ingestion.amazon_identifiers import AMAZON_ASIN_PATTERN, extract_amazon_asin_from_url, normalize_asin

AMAZON_ES_HOST = "amazon.es"
MIN_ACCEPTED_PRICE_EUR = Decimal("12.00")
BORDERLINE_PRICE_EUR = Decimal("10.00")
DEFAULT_DISCOVERY_TIMEOUT = 20.0
MAX_RECOVERED_MISSING_PRICE_CANDIDATES = 20
DEFAULT_MAX_PAGINATION_PAGES = 5
BEST_EFFORT_SOURCE_TYPES = frozenset({"deals"})
PRICE_SENSITIVE_SOURCE_TYPES = frozenset(
    {"best_sellers", "movers_and_shakers", "new_releases", "most_wished_for"}
)

PRICE_PATTERNS = [
    re.compile(r"€\s*([0-9]+(?:[.\s\xa0][0-9]{3})*(?:,[0-9]{2})?)"),
    re.compile(r"([0-9]+(?:[.\s\xa0][0-9]{3})*(?:,[0-9]{2})?)\s*€"),
    re.compile(r"\bEUR\s*([0-9]+(?:[.\s\xa0][0-9]{3})*(?:,[0-9]{2})?)", re.IGNORECASE),
]
WHOLE_FRACTION_PATTERNS = [
    re.compile(
        r'a-price-whole[^>]*>\s*([0-9]+(?:[.\s\xa0][0-9]{3})?)\s*<.*?a-price-fraction[^>]*>\s*([0-9]{2})',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'whole[^>]*>\s*([0-9]+(?:[.\s\xa0][0-9]{3})?)\s*<.*?fraction[^>]*>\s*([0-9]{2})',
        re.IGNORECASE | re.DOTALL,
    ),
]
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
DATA_ASIN_PATTERN = re.compile(r'data-asin=["\']([^"\']+)["\']', re.IGNORECASE)
ANCHOR_TAG_PATTERN = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a>", re.IGNORECASE | re.DOTALL)
ATTRIBUTE_PATTERN = re.compile(
    r"""([a-zA-Z_:][a-zA-Z0-9_:\-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""",
    re.DOTALL,
)
TITLE_PATTERNS = [
    re.compile(r'aria-label=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'title=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'alt=["\']([^"\']+)["\']', re.IGNORECASE),
]
TRAILING_PRICE_PATTERN = re.compile(r"\s+[0-9]+(?:[.,][0-9]{2})?\s*€\s*$", re.IGNORECASE)
PLACEHOLDER_TITLE_PATTERNS = [
    re.compile(r"data-a-carousel-options", re.IGNORECASE),
    re.compile(r"\\\"id\\\":\\\"", re.IGNORECASE),
    re.compile(r"pd_rd_i", re.IGNORECASE),
    re.compile(r"^\d{10,}", re.IGNORECASE),
    re.compile(r"a-carousel-controls", re.IGNORECASE),
    re.compile(r"a-link-normal", re.IGNORECASE),
    re.compile(r"p13n-sc-uncoverable-faceout", re.IGNORECASE),
    re.compile(r"""href="/""", re.IGNORECASE),
    re.compile(r"""src="https?://""", re.IGNORECASE),
]
LOW_SIGNAL_TITLE_PATTERNS = [
    re.compile(r"\b(cucarach|hormig|antihormig|mosquit|insecticida|repelente de insect|ratas|ratones|raton|roedor)\b"),
    re.compile(r"\b(creatina|magnesio|omega\s*3|omega-3|whey|protein|proteina|suplemento|bisglicinato|monohidrato)\b"),
]
LOW_SIGNAL_URL_PATTERNS = [
    re.compile(r"(cucarach|hormig|mosquit|insecticida|ratas|ratones|raton|roedor)"),
    re.compile(r"(creatina|magnesio|omega-?3|whey|protein|proteina|suplemento|bisglicinato|monohidrato)"),
]
RECOVERABLE_MISSING_PRICE_TITLE_PATTERNS = [
    re.compile(r"\b(monitor|ssd|iphone|xiaomi|logitech|anker|sony)\b"),
]
RECOVERABLE_MISSING_PRICE_URL_PATTERNS = [
    re.compile(r"(monitor|ssd|iphone|xiaomi|logitech|anker|sony)"),
]
RECOVERABLE_MISSING_PRICE_CATEGORY_URL_PATTERNS = [
    re.compile(r"(electronica|electronics|informatica|computers|accesorios-tecnologia|videojuegos)"),
]
PAGINATION_PAGE_PATTERNS = [
    re.compile(r"[?&]pg=(\d+)\b", re.IGNORECASE),
    re.compile(r"[?&]page=(\d+)\b", re.IGNORECASE),
    re.compile(r"[_/-]pg[_=-]?(\d+)\b", re.IGNORECASE),
]


@dataclass(slots=True)
class _RawCandidate:
    asin: str
    product_url: str | None
    title: str | None
    context_fragment: str
    anchor_offset: int


@dataclass(slots=True)
class AmazonEsCandidate:
    asin: str
    title: str | None
    price_eur: Decimal | None
    product_url: str | None
    source_url: str
    source_type: str
    issues: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "asin": self.asin,
            "title": self.title,
            "price_eur": str(self.price_eur) if self.price_eur is not None else None,
            "product_url": self.product_url,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "issues": self.issues,
        }


@dataclass(slots=True)
class AmazonEsRejectedCandidate:
    asin: str | None
    title: str | None
    price_eur: Decimal | None
    product_url: str | None
    source_url: str
    source_type: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "asin": self.asin,
            "title": self.title,
            "price_eur": str(self.price_eur) if self.price_eur is not None else None,
            "product_url": self.product_url,
            "source_url": self.source_url,
            "source_type": self.source_type,
            "reason": self.reason,
        }


@dataclass(slots=True)
class AmazonEsDiscoveryResult:
    source_url: str
    source_type: str
    raw_candidate_count: int
    accepted_candidates: list[AmazonEsCandidate]
    rejected_candidates: list[AmazonEsRejectedCandidate]
    page_issues: list[str] = field(default_factory=list)

    @property
    def accepted_asins(self) -> list[str]:
        return [candidate.asin for candidate in self.accepted_candidates]

    @property
    def accepted_candidate_count(self) -> int:
        return len(self.accepted_candidates)

    @property
    def rejected_candidate_count(self) -> int:
        return len(self.rejected_candidates)

    @property
    def accepted_with_price_count(self) -> int:
        return sum(1 for candidate in self.accepted_candidates if candidate.price_eur is not None)

    @property
    def accepted_borderline_count(self) -> int:
        return sum(1 for candidate in self.accepted_candidates if "borderline_price" in candidate.issues)

    @property
    def accepted_price_missing_count(self) -> int:
        return sum(1 for candidate in self.accepted_candidates if candidate.price_eur is None)

    @property
    def accepted_price_missing_recovered_count(self) -> int:
        return sum(
            1 for candidate in self.accepted_candidates if "price_missing_recovered" in candidate.issues
        )

    @property
    def recovered_asins(self) -> list[str]:
        return [
            candidate.asin for candidate in self.accepted_candidates if "price_missing_recovered" in candidate.issues
        ]

    @property
    def accepted_standard_count(self) -> int:
        return (
            self.accepted_candidate_count
            - self.accepted_price_missing_recovered_count
            - self.accepted_borderline_count
        )

    @property
    def counts_by_reason(self) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for issue in self.page_issues:
            counts[issue] += 1
        for candidate in self.accepted_candidates:
            for issue in candidate.issues:
                counts[issue] += 1
        for candidate in self.rejected_candidates:
            counts[candidate.reason] += 1
        return dict(sorted(counts.items()))

    def as_dict(self, *, include_candidates: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source_url": self.source_url,
            "source_type": self.source_type,
            "raw_candidate_count": self.raw_candidate_count,
            "accepted_candidate_count": self.accepted_candidate_count,
            "rejected_candidate_count": self.rejected_candidate_count,
            "accepted_standard_count": self.accepted_standard_count,
            "accepted_borderline_count": self.accepted_borderline_count,
            "accepted_with_price_count": self.accepted_with_price_count,
            "accepted_price_missing_count": self.accepted_price_missing_count,
            "accepted_price_missing_recovered_count": self.accepted_price_missing_recovered_count,
            "recovered_asins": self.recovered_asins,
            "counts_by_reason": self.counts_by_reason,
            "accepted_asins": self.accepted_asins,
            "page_issues": self.page_issues,
        }
        if include_candidates:
            payload["accepted_candidates"] = [candidate.as_dict() for candidate in self.accepted_candidates]
            payload["rejected_candidates"] = [candidate.as_dict() for candidate in self.rejected_candidates]
        return payload


@dataclass(slots=True)
class AmazonEsPaginatedDiscoveryResult:
    source_url: str
    source_type: str
    page_results: list[AmazonEsDiscoveryResult]

    @property
    def fetched_page_count(self) -> int:
        return len(self.page_results)

    @property
    def accepted_asins(self) -> list[str]:
        accepted: list[str] = []
        seen: set[str] = set()
        for result in self.page_results:
            for asin in result.accepted_asins:
                if asin in seen:
                    continue
                seen.add(asin)
                accepted.append(asin)
        return accepted

    @property
    def total_unique_asin_count(self) -> int:
        return len(self.accepted_asins)

    def as_dict(self, *, include_candidates: bool = False) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "source_type": self.source_type,
            "fetched_page_count": self.fetched_page_count,
            "total_unique_asin_count": self.total_unique_asin_count,
            "page_summaries": [
                {
                    "page_number": _infer_page_number(result.source_url) or index + 1,
                    "source_url": result.source_url,
                    "raw_candidate_count": result.raw_candidate_count,
                    "accepted_candidate_count": result.accepted_candidate_count,
                    "accepted_asin_count": len(result.accepted_asins),
                    "accepted_asins": result.accepted_asins,
                    "counts_by_reason": result.counts_by_reason,
                }
                for index, result in enumerate(self.page_results)
            ],
            "accepted_asins": self.accepted_asins,
            "accepted_candidate_count": sum(result.accepted_candidate_count for result in self.page_results),
            "rejected_candidate_count": sum(result.rejected_candidate_count for result in self.page_results),
            "counts_by_reason": _merge_counts(result.counts_by_reason for result in self.page_results),
            "pages": [result.as_dict(include_candidates=include_candidates) for result in self.page_results]
            if include_candidates
            else None,
        }


@dataclass(slots=True)
class AmazonEsCandidatePoolPage:
    source_url: str
    source_type: str
    raw_candidate_count: int
    candidates: list[AmazonEsCandidate]
    rejected_candidates: list[AmazonEsRejectedCandidate]
    page_issues: list[str] = field(default_factory=list)

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def candidate_asins(self) -> list[str]:
        return [candidate.asin for candidate in self.candidates]


@dataclass(slots=True)
class AmazonEsDiscoveryQualityReport:
    source_url: str
    source_type: str
    raw_candidate_count: int
    unique_candidate_count: int
    accepted_candidate_count: int
    candidates_with_price_count: int
    issue_counts: dict[str, int]
    extraction_success_rate: float
    price_coverage_rate: float
    acceptance_rate: float
    status: str
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_url": self.source_url,
            "source_type": self.source_type,
            "raw_candidate_count": self.raw_candidate_count,
            "unique_candidate_count": self.unique_candidate_count,
            "accepted_candidate_count": self.accepted_candidate_count,
            "candidates_with_price_count": self.candidates_with_price_count,
            "issue_counts": self.issue_counts,
            "extraction_success_rate": round(self.extraction_success_rate, 4),
            "price_coverage_rate": round(self.price_coverage_rate, 4),
            "acceptance_rate": round(self.acceptance_rate, 4),
            "status": self.status,
            "reasons": self.reasons,
        }


def assess_discovery_quality(
    *,
    source_url: str,
    source_type: str,
    raw_candidate_count: int,
    unique_candidate_count: int,
    accepted_candidate_count: int,
    candidates_with_price_count: int,
    issue_counts: dict[str, int] | None = None,
) -> AmazonEsDiscoveryQualityReport:
    counts = dict(sorted((issue_counts or {}).items()))
    missing_asin_count = counts.get("missing_asin", 0) + counts.get("invalid_asin_pattern", 0)
    extraction_opportunities = raw_candidate_count + missing_asin_count
    extraction_success_rate = (
        raw_candidate_count / extraction_opportunities if extraction_opportunities > 0 else 1.0
    )
    price_coverage_rate = (
        candidates_with_price_count / unique_candidate_count if unique_candidate_count > 0 else 0.0
    )
    acceptance_rate = accepted_candidate_count / unique_candidate_count if unique_candidate_count > 0 else 0.0

    status = "healthy"
    reasons: list[str] = []

    if extraction_opportunities >= 10 and extraction_success_rate < 0.20:
        status = "low_quality"
        reasons.append("low_asin_extraction_rate")
    elif extraction_opportunities >= 5 and extraction_success_rate < 0.45:
        status = "warning"
        reasons.append("degraded_asin_extraction_rate")

    if source_type in PRICE_SENSITIVE_SOURCE_TYPES:
        if unique_candidate_count >= 10 and price_coverage_rate < 0.05:
            status = "low_quality"
            reasons.append("low_price_coverage")
        elif unique_candidate_count >= 5 and price_coverage_rate < 0.20 and status != "low_quality":
            status = "warning"
            reasons.append("degraded_price_coverage")

    if counts.get("unsupported_source_type", 0) > 0 and status == "healthy":
        status = "warning"
        reasons.append("unsupported_source_type")

    return AmazonEsDiscoveryQualityReport(
        source_url=source_url,
        source_type=source_type,
        raw_candidate_count=raw_candidate_count,
        unique_candidate_count=unique_candidate_count,
        accepted_candidate_count=accepted_candidate_count,
        candidates_with_price_count=candidates_with_price_count,
        issue_counts=counts,
        extraction_success_rate=extraction_success_rate,
        price_coverage_rate=price_coverage_rate,
        acceptance_rate=acceptance_rate,
        status=status,
        reasons=reasons,
    )


def fetch_amazon_es_page(
    url: str,
    *,
    timeout: float = DEFAULT_DISCOVERY_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout, follow_redirects=True, headers=headers)
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.text
    finally:
        if owns_client:
            client.close()


def classify_amazon_es_source_type(url: str) -> str:
    try:
        parsed = urlparse(url)
    except ValueError:
        return "unknown"

    host = (parsed.netloc or "").casefold()
    if AMAZON_ES_HOST not in host:
        return "unknown"

    path = (parsed.path or "").casefold()
    if "/gp/bestsellers" in path or "/bestsellers" in path:
        return "best_sellers"
    if "/gp/movers-and-shakers" in path or "/movers-and-shakers" in path:
        return "movers_and_shakers"
    if "/gp/new-releases" in path or "/new-releases" in path:
        return "new_releases"
    if "/gp/most-wished-for" in path or "/most-wished-for" in path:
        return "most_wished_for"
    if "/deals" in path or "/gp/goldbox" in path:
        return "deals"
    return "unknown"


def discover_source_url(
    source_url: str,
    *,
    max_candidates: int | None = None,
    max_recovered_missing_price_candidates: int = MAX_RECOVERED_MISSING_PRICE_CANDIDATES,
    timeout: float = DEFAULT_DISCOVERY_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> AmazonEsDiscoveryResult:
    html = fetch_amazon_es_page(source_url, timeout=timeout, http_client=http_client)
    return discover_candidates_from_html(
        html,
        source_url=source_url,
        max_candidates=max_candidates,
        max_recovered_missing_price_candidates=max_recovered_missing_price_candidates,
    )


def discover_source_with_pagination(
    source_url: str,
    *,
    max_candidates: int | None = None,
    max_pages: int = DEFAULT_MAX_PAGINATION_PAGES,
    max_recovered_missing_price_candidates: int = MAX_RECOVERED_MISSING_PRICE_CANDIDATES,
    timeout: float = DEFAULT_DISCOVERY_TIMEOUT,
    http_client: httpx.Client | None = None,
) -> AmazonEsPaginatedDiscoveryResult:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
    }
    owns_client = http_client is None
    client = http_client or httpx.Client(timeout=timeout, follow_redirects=True, headers=headers)
    try:
        return _discover_with_client(
            source_url,
            max_candidates=max_candidates,
            max_pages=max_pages,
            max_recovered_missing_price_candidates=max_recovered_missing_price_candidates,
            http_client=client,
        )
    finally:
        if owns_client:
            client.close()


def discover_candidates_from_html(
    html: str,
    *,
    source_url: str,
    max_candidates: int | None = None,
    max_recovered_missing_price_candidates: int = MAX_RECOVERED_MISSING_PRICE_CANDIDATES,
) -> AmazonEsDiscoveryResult:
    candidate_pool = discover_candidate_pool_from_html(html, source_url=source_url)
    return filter_candidate_pool(
        candidate_pool.candidates,
        source_url=source_url,
        source_type=candidate_pool.source_type,
        raw_candidate_count=candidate_pool.raw_candidate_count,
        page_issues=candidate_pool.page_issues,
        duplicate_rejections=candidate_pool.rejected_candidates,
        max_candidates=max_candidates,
        max_recovered_missing_price_candidates=max_recovered_missing_price_candidates,
    )


def discover_candidate_pool_from_html(
    html: str,
    *,
    source_url: str,
) -> AmazonEsCandidatePoolPage:
    source_type = classify_amazon_es_source_type(source_url)
    page_issues: list[str] = []
    if source_type == "unknown":
        page_issues.append("unsupported_source_type")

    raw_candidates: list[_RawCandidate] = []
    for anchor in _extract_anchor_elements(html):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        absolute_url = urljoin(source_url, href)
        asin = extract_amazon_asin_from_url(absolute_url)
        if asin is None:
            if _looks_like_amazon_product_link(absolute_url):
                page_issues.append("missing_asin" if "/dp/" not in absolute_url and "/gp/product/" not in absolute_url else "invalid_asin_pattern")
            elif _looks_like_amazon_es_link(absolute_url):
                page_issues.append("non_amazon_product_link")
            continue
        if not _looks_like_amazon_es_link(absolute_url):
            page_issues.append("non_amazon_product_link")
            continue
        title = _first_non_empty(anchor.get("aria_label"), anchor.get("title"), anchor.get("text"))
        context_fragment, anchor_offset = _context_fragment_for_range(
            html,
            start=int(anchor["start"]),
            end=int(anchor["end"]),
        )
        raw_candidates.append(
            _RawCandidate(
                asin=asin,
                product_url=absolute_url,
                title=title,
                context_fragment=context_fragment,
                anchor_offset=anchor_offset,
            )
        )

    for raw_match in DATA_ASIN_PATTERN.finditer(html):
        raw_asin = raw_match.group(1)
        if not raw_asin:
            continue
        asin = normalize_asin(raw_asin)
        if asin is None:
            page_issues.append("invalid_asin_pattern")
            continue
        context_fragment, anchor_offset = _context_fragment_for_index(html, index=raw_match.start())
        raw_candidates.append(
            _RawCandidate(
                asin=asin,
                product_url=f"https://www.{AMAZON_ES_HOST}/dp/{asin}",
                title=None,
                context_fragment=context_fragment,
                anchor_offset=anchor_offset,
            )
        )

    raw_candidate_count = len(raw_candidates)
    merged_candidates, duplicate_rejections = _merge_raw_candidates(
        raw_candidates,
        source_url=source_url,
        source_type=source_type,
    )
    return AmazonEsCandidatePoolPage(
        source_url=source_url,
        source_type=source_type,
        raw_candidate_count=raw_candidate_count,
        candidates=merged_candidates,
        rejected_candidates=duplicate_rejections,
        page_issues=page_issues,
    )


def filter_candidate_pool(
    candidates: list[AmazonEsCandidate],
    *,
    source_url: str,
    source_type: str,
    raw_candidate_count: int,
    page_issues: list[str] | None = None,
    duplicate_rejections: list[AmazonEsRejectedCandidate] | None = None,
    max_candidates: int | None = None,
    max_recovered_missing_price_candidates: int = MAX_RECOVERED_MISSING_PRICE_CANDIDATES,
) -> AmazonEsDiscoveryResult:
    accepted: list[AmazonEsCandidate] = []
    rejected: list[AmazonEsRejectedCandidate] = list(duplicate_rejections or [])
    recovered_missing_price_count = 0

    for original_candidate in candidates:
        merged_candidate = AmazonEsCandidate(
            asin=original_candidate.asin,
            title=original_candidate.title,
            price_eur=original_candidate.price_eur,
            product_url=original_candidate.product_url,
            source_url=original_candidate.source_url,
            source_type=original_candidate.source_type,
            issues=list(original_candidate.issues),
        )
        if _is_low_signal_candidate(merged_candidate.title, merged_candidate.product_url):
            rejected.append(
                AmazonEsRejectedCandidate(
                    asin=merged_candidate.asin,
                    title=merged_candidate.title,
                    price_eur=merged_candidate.price_eur,
                    product_url=merged_candidate.product_url,
                    source_url=source_url,
                    source_type=source_type,
                    reason="category_filtered_low_signal",
                )
            )
            continue

        if merged_candidate.price_eur is not None:
            if merged_candidate.price_eur < BORDERLINE_PRICE_EUR:
                rejected.append(
                    AmazonEsRejectedCandidate(
                        asin=merged_candidate.asin,
                        title=merged_candidate.title,
                        price_eur=merged_candidate.price_eur,
                        product_url=merged_candidate.product_url,
                        source_url=source_url,
                        source_type=source_type,
                        reason="price_below_threshold",
                    )
                )
                continue
            if merged_candidate.price_eur < MIN_ACCEPTED_PRICE_EUR:
                merged_candidate.issues.append("borderline_price")

        if merged_candidate.price_eur is None:
            if _is_recoverable_missing_price_candidate(merged_candidate) and (
                recovered_missing_price_count < max_recovered_missing_price_candidates
            ):
                if "price_missing" in merged_candidate.issues:
                    merged_candidate.issues = [
                        "price_missing_recovered" if issue == "price_missing" else issue
                        for issue in merged_candidate.issues
                    ]
                recovered_missing_price_count += 1
            else:
                rejected.append(
                    AmazonEsRejectedCandidate(
                        asin=merged_candidate.asin,
                        title=merged_candidate.title,
                        price_eur=merged_candidate.price_eur,
                        product_url=merged_candidate.product_url,
                        source_url=source_url,
                        source_type=source_type,
                        reason="price_missing",
                    )
                )
                continue

        accepted.append(merged_candidate)

        if max_candidates is not None and len(accepted) >= max_candidates:
            break

    return AmazonEsDiscoveryResult(
        source_url=source_url,
        source_type=source_type,
        raw_candidate_count=raw_candidate_count,
        accepted_candidates=accepted,
        rejected_candidates=rejected,
        page_issues=list(page_issues or []),
    )


def _discover_with_client(
    source_url: str,
    *,
    max_candidates: int | None,
    max_pages: int,
    max_recovered_missing_price_candidates: int,
    http_client: httpx.Client,
) -> AmazonEsPaginatedDiscoveryResult:
    source_type = classify_amazon_es_source_type(source_url)
    queue: list[str] = [source_url]
    visited_urls: set[str] = set()
    seen_accepted_asins: set[str] = set()
    page_results: list[AmazonEsDiscoveryResult] = []
    recovered_missing_price_count = 0

    while queue and len(page_results) < max_pages:
        page_url = queue.pop(0)
        normalized_page_url = _normalize_page_url(page_url)
        if normalized_page_url in visited_urls:
            continue
        visited_urls.add(normalized_page_url)

        html = fetch_amazon_es_page(page_url, http_client=http_client)
        page_result = discover_candidates_from_html(
            html,
            source_url=page_url,
            max_candidates=None,
            max_recovered_missing_price_candidates=max(
                max_recovered_missing_price_candidates - recovered_missing_price_count,
                0,
            ),
        )
        remaining = None if max_candidates is None else max(max_candidates - len(seen_accepted_asins), 0)
        deduped_result, new_asin_count = _dedupe_page_result(page_result, seen_accepted_asins, remaining=remaining)
        page_results.append(deduped_result)
        recovered_missing_price_count += deduped_result.accepted_price_missing_recovered_count

        if max_candidates is not None and len(seen_accepted_asins) >= max_candidates:
            break
        if new_asin_count == 0:
            break

        for next_url in discover_pagination_urls_from_html(html, current_url=page_url):
            normalized_next_url = _normalize_page_url(next_url)
            if normalized_next_url in visited_urls or any(_normalize_page_url(item) == normalized_next_url for item in queue):
                continue
            if classify_amazon_es_source_type(next_url) != source_type:
                continue
            queue.append(next_url)

    return AmazonEsPaginatedDiscoveryResult(
        source_url=source_url,
        source_type=source_type,
        page_results=page_results,
    )


def discover_pagination_urls_from_html(html: str, *, current_url: str) -> list[str]:
    source_type = classify_amazon_es_source_type(current_url)
    if source_type not in {"best_sellers", "movers_and_shakers", "new_releases", "most_wished_for"}:
        return []

    current_page = _infer_page_number(current_url) or 1
    candidates: dict[int, str] = {}
    for anchor in _extract_anchor_elements(html):
        href = str(anchor.get("href") or "").strip()
        if not href:
            continue
        absolute_url = urljoin(current_url, href)
        if classify_amazon_es_source_type(absolute_url) != source_type:
            continue
        page_number = _infer_page_number(absolute_url)
        if page_number is None or page_number <= current_page:
            continue
        candidates.setdefault(page_number, absolute_url)

    return [candidates[page_number] for page_number in sorted(candidates)]


def _infer_page_number(url: str) -> int | None:
    decoded = unquote(url)
    for pattern in PAGINATION_PAGE_PATTERNS:
        match = pattern.search(decoded)
        if not match:
            continue
        try:
            page_number = int(match.group(1))
        except ValueError:
            continue
        if page_number >= 1:
            return page_number
    return None


def _normalize_page_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    if parsed.query:
        return f"{parsed.scheme}://{parsed.netloc.casefold()}{path}?{parsed.query}"
    return f"{parsed.scheme}://{parsed.netloc.casefold()}{path}"


def _dedupe_page_result(
    result: AmazonEsDiscoveryResult,
    seen_accepted_asins: set[str],
    *,
    remaining: int | None,
) -> tuple[AmazonEsDiscoveryResult, int]:
    accepted_candidates: list[AmazonEsCandidate] = []
    rejected_candidates = list(result.rejected_candidates)
    new_asin_count = 0

    for candidate in result.accepted_candidates:
        if candidate.asin in seen_accepted_asins:
            rejected_candidates.append(
                AmazonEsRejectedCandidate(
                    asin=candidate.asin,
                    title=candidate.title,
                    price_eur=candidate.price_eur,
                    product_url=candidate.product_url,
                    source_url=result.source_url,
                    source_type=result.source_type,
                    reason="duplicate_asin",
                )
            )
            continue
        if remaining is not None and len(accepted_candidates) >= remaining:
            break
        accepted_candidates.append(candidate)
        seen_accepted_asins.add(candidate.asin)
        new_asin_count += 1

    return (
        AmazonEsDiscoveryResult(
            source_url=result.source_url,
            source_type=result.source_type,
            raw_candidate_count=result.raw_candidate_count,
            accepted_candidates=accepted_candidates,
            rejected_candidates=rejected_candidates,
            page_issues=result.page_issues,
        ),
        new_asin_count,
    )


def _merge_raw_candidates(
    raw_candidates: list[_RawCandidate],
    *,
    source_url: str,
    source_type: str,
) -> tuple[list[AmazonEsCandidate], list[AmazonEsRejectedCandidate]]:
    merged_by_asin: dict[str, AmazonEsCandidate] = {}
    ordered_asins: list[str] = []
    rejected: list[AmazonEsRejectedCandidate] = []

    for candidate in raw_candidates:
        resolved_title = _resolve_candidate_title(
            explicit_title=candidate.title,
            context_fragment=candidate.context_fragment,
            product_url=candidate.product_url,
        )
        price_eur = _extract_price_eur(candidate.context_fragment, anchor_offset=candidate.anchor_offset)

        existing = merged_by_asin.get(candidate.asin)
        if existing is not None:
            existing.title = _prefer_title(existing.title, resolved_title)
            existing.price_eur = _prefer_price(existing.price_eur, price_eur)
            existing.product_url = _prefer_product_url(existing.product_url, candidate.product_url)
            _refresh_candidate_issues(existing)
            rejected.append(
                AmazonEsRejectedCandidate(
                    asin=candidate.asin,
                    title=resolved_title,
                    price_eur=price_eur,
                    product_url=candidate.product_url,
                    source_url=source_url,
                    source_type=source_type,
                    reason="duplicate_asin",
                )
            )
            continue

        merged_candidate = AmazonEsCandidate(
            asin=candidate.asin,
            title=resolved_title,
            price_eur=price_eur,
            product_url=candidate.product_url,
            source_url=source_url,
            source_type=source_type,
            issues=[],
        )
        _refresh_candidate_issues(merged_candidate)
        merged_by_asin[candidate.asin] = merged_candidate
        ordered_asins.append(candidate.asin)

    return [merged_by_asin[asin] for asin in ordered_asins], rejected


def _merge_counts(counts_iterable: Iterable[dict[str, int]]) -> dict[str, int]:
    merged: Counter[str] = Counter()
    for counts in counts_iterable:
        merged.update(counts)
    return dict(sorted(merged.items()))


def _context_fragment_for_index(html: str, *, index: int, window: int = 1200) -> tuple[str, int]:
    start = max(index - window // 2, 0)
    end = min(index + window // 2, len(html))
    return html[start:end], index - start


def _context_fragment_for_range(html: str, *, start: int, end: int, window: int = 1200) -> tuple[str, int]:
    padding = max(window - (end - start), 0) // 2
    bounded_start = max(start - padding, 0)
    bounded_end = min(end + padding, len(html))
    anchor_offset = ((start + end) // 2) - bounded_start
    return html[bounded_start:bounded_end], anchor_offset


def _extract_anchor_elements(html: str) -> list[dict[str, object]]:
    anchors: list[dict[str, object]] = []
    for match in ANCHOR_TAG_PATTERN.finditer(html):
        attrs_raw = match.group("attrs") or ""
        attrs: dict[str, str] = {}
        for attribute_match in ATTRIBUTE_PATTERN.finditer(attrs_raw):
            name = (attribute_match.group(1) or "").casefold()
            value = attribute_match.group(2) if attribute_match.group(2) is not None else attribute_match.group(3)
            if name:
                attrs[name] = unescape(value or "")
        href = attrs.get("href")
        if not href:
            continue
        anchors.append(
            {
                "href": href,
                "aria_label": attrs.get("aria-label"),
                "title": attrs.get("title"),
                "text": _strip_html(match.group("body") or ""),
                "start": match.start(),
                "end": match.end(),
            }
        )
    return anchors


def _extract_title_from_fragment(fragment: str) -> str | None:
    for pattern in TITLE_PATTERNS:
        match = pattern.search(fragment)
        if match:
            cleaned = _clean_text(match.group(1))
            if cleaned and not _is_placeholder_title(cleaned):
                return cleaned
    stripped = _strip_html(fragment)
    cleaned = _clean_text(stripped)
    if cleaned and not _is_placeholder_title(cleaned):
        return cleaned[:160]
    return None


def _extract_price_eur(fragment: str, *, anchor_offset: int | None = None) -> Decimal | None:
    for pattern in WHOLE_FRACTION_PATTERNS:
        match = pattern.search(fragment)
        if match:
            parsed = _parse_euro_amount(f"{match.group(1)},{match.group(2)}")
            if parsed is not None:
                return parsed

    best_match = _nearest_price_match(fragment, anchor_offset=anchor_offset)
    if best_match is not None:
        return best_match

    haystack = _strip_html(fragment)
    return _nearest_price_match(haystack, anchor_offset=None)


def _nearest_price_match(haystack: str, *, anchor_offset: int | None) -> Decimal | None:
    anchor_index = anchor_offset if anchor_offset is not None else len(haystack) // 2
    best_match: tuple[int, Decimal] | None = None
    for pattern in PRICE_PATTERNS:
        for match in pattern.finditer(haystack):
            if _is_offer_from_price_context(haystack, match.start()):
                continue
            parsed = _parse_euro_amount(match.group(1))
            if parsed is None:
                continue
            distance = abs(match.start() - anchor_index)
            if best_match is None or distance < best_match[0]:
                best_match = (distance, parsed)
    return best_match[1] if best_match is not None else None


def _parse_euro_amount(raw_value: str) -> Decimal | None:
    cleaned = raw_value.replace("\xa0", "").replace(" ", "").replace(".", "").replace(",", ".")
    try:
        return Decimal(cleaned)
    except (InvalidOperation, ValueError):
        return None


def _strip_html(value: str) -> str:
    return _clean_text(HTML_TAG_PATTERN.sub(" ", unescape(value)))


def _clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(unescape(value).split())
    return cleaned or None


def _resolve_candidate_title(
    *,
    explicit_title: str | None,
    context_fragment: str,
    product_url: str | None,
) -> str | None:
    resolved_title = explicit_title
    if not resolved_title or _is_placeholder_title(resolved_title):
        resolved_title = _extract_title_from_fragment(context_fragment)
    if not resolved_title or _is_placeholder_title(resolved_title):
        resolved_title = _title_from_product_url(product_url)
    return _cleanup_title(resolved_title)


def _refresh_candidate_issues(candidate: AmazonEsCandidate) -> None:
    issues: list[str] = []
    if candidate.price_eur is None:
        issues.append("price_missing")
    if not candidate.title:
        issues.append("source_parse_partial")
    candidate.issues = issues


def _prefer_title(current_title: str | None, candidate_title: str | None) -> str | None:
    current = _cleanup_title(current_title)
    candidate = _cleanup_title(candidate_title)
    if candidate is None:
        return current
    if current is None:
        return candidate
    if _title_quality(candidate) > _title_quality(current):
        return candidate
    if _title_quality(candidate) == _title_quality(current) and len(candidate) > len(current):
        return candidate
    return current


def _prefer_price(current_price: Decimal | None, candidate_price: Decimal | None) -> Decimal | None:
    if current_price is None:
        return candidate_price
    return current_price


def _prefer_product_url(current_url: str | None, candidate_url: str | None) -> str | None:
    if candidate_url is None:
        return current_url
    if current_url is None:
        return candidate_url
    if _is_canonical_asin_url(current_url) and not _is_canonical_asin_url(candidate_url):
        return candidate_url
    return current_url


def _title_from_product_url(product_url: str | None) -> str | None:
    if not product_url:
        return None
    try:
        parsed = urlparse(product_url)
    except ValueError:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    if "dp" not in parts:
        return None
    dp_index = parts.index("dp")
    if dp_index == 0:
        return None
    slug = _clean_text(unquote(parts[dp_index - 1]).replace("-", " ").replace("_", " "))
    if not slug or _is_placeholder_title(slug):
        return None
    return slug


def _is_canonical_asin_url(product_url: str) -> bool:
    try:
        parsed = urlparse(product_url)
    except ValueError:
        return False
    parts = [part for part in parsed.path.split("/") if part]
    return len(parts) >= 2 and parts[-2] == "dp" and AMAZON_ASIN_PATTERN.fullmatch(parts[-1].upper()) is not None


def _is_placeholder_title(value: str | None) -> bool:
    cleaned = _clean_text(value)
    if not cleaned:
        return True
    return any(pattern.search(cleaned) for pattern in PLACEHOLDER_TITLE_PATTERNS)


def _cleanup_title(value: str | None) -> str | None:
    cleaned = _clean_text(value)
    if not cleaned:
        return None
    cleaned = TRAILING_PRICE_PATTERN.sub("", cleaned).strip()
    return cleaned or None


def _title_quality(value: str | None) -> int:
    cleaned = _cleanup_title(value)
    if not cleaned or _is_placeholder_title(cleaned):
        return 0
    signal = _normalized_signal_text(cleaned)
    if "€" in cleaned or "ofertas desde" in signal:
        return 1
    return 2


def _normalized_signal_text(value: str | None) -> str:
    cleaned = _clean_text(value)
    if not cleaned:
        return ""
    decomposed = normalize("NFKD", cleaned.casefold())
    return "".join(character for character in decomposed if not combining(character))


def _is_offer_from_price_context(haystack: str, match_start: int) -> bool:
    context_start = max(match_start - 40, 0)
    context = _normalized_signal_text(haystack[context_start : match_start + 20])
    return "ofertas desde" in context or "oferta desde" in context or "offers from" in context


def _is_low_signal_candidate(title: str | None, product_url: str | None) -> bool:
    title_signal = _normalized_signal_text(title)
    url_signal = _normalized_signal_text(_title_from_product_url(product_url) or product_url)
    return any(pattern.search(title_signal) for pattern in LOW_SIGNAL_TITLE_PATTERNS) or any(
        pattern.search(url_signal) for pattern in LOW_SIGNAL_URL_PATTERNS
    )


def _is_recoverable_missing_price_candidate(candidate: AmazonEsCandidate) -> bool:
    title_signal = _normalized_signal_text(candidate.title)
    url_signal = _normalized_signal_text(_title_from_product_url(candidate.product_url) or candidate.product_url)
    return (
        any(pattern.search(title_signal) for pattern in RECOVERABLE_MISSING_PRICE_TITLE_PATTERNS)
        or any(pattern.search(url_signal) for pattern in RECOVERABLE_MISSING_PRICE_URL_PATTERNS)
        or any(pattern.search(url_signal) for pattern in RECOVERABLE_MISSING_PRICE_CATEGORY_URL_PATTERNS)
    )


def _first_non_empty(*values: object) -> str | None:
    for value in values:
        cleaned = _clean_text(str(value)) if value is not None else None
        if cleaned:
            return cleaned
    return None


def _looks_like_amazon_es_link(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    return AMAZON_ES_HOST in (parsed.netloc or "").casefold()


def _looks_like_amazon_product_link(url: str) -> bool:
    try:
        parsed = urlparse(url)
    except ValueError:
        return False
    if "amazon." not in (parsed.netloc or "").casefold():
        return False
    if "/dp/" in parsed.path or "/gp/product/" in parsed.path:
        return True
    return any(AMAZON_ASIN_PATTERN.fullmatch(part.upper()) for part in parsed.path.split("/") if part)
