from app.matching.service import MatchingService
from app.ai.client import ModelClient, StubModelClient
from app.ai.service import AICopyGenerationService
from app.ingestion.normalization import DefaultRecordNormalizer
from app.ingestion.parsers.affiliate_feed import AffiliateFeedCSVParser
from app.ingestion.parsers.keepa import KeepaParser
from app.ingestion.service import IngestionService
from app.services.deal_service import DealQueryService
from app.services.review_service import ReviewService


def get_deal_query_service() -> DealQueryService:
    return DealQueryService()


def get_review_service() -> ReviewService:
    return ReviewService()


def get_model_client() -> ModelClient:
    return StubModelClient(
        '{"title":"Draft unavailable","summary":"No model client configured.","verdict":"not_supported","tags":["review-needed"]}'
    )


def get_ai_copy_service() -> AICopyGenerationService:
    return AICopyGenerationService(client=get_model_client())


def get_ingestion_service(parser_name: str) -> IngestionService:
    parsers = {
        "keepa": KeepaParser(),
        "affiliate_csv": AffiliateFeedCSVParser(),
    }
    parser = parsers[parser_name]
    return IngestionService(
        parser=parser,
        normalizer=DefaultRecordNormalizer(),
        matcher=MatchingService(),
    )
