from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.ingestion.schemas import NormalizedIngestionRecord, ParsedSourceRecord


class SourceParser(ABC):
    parser_name: str

    @abstractmethod
    def parse(self, payload: Any) -> list[ParsedSourceRecord]:
        raise NotImplementedError


class RecordNormalizer(ABC):
    @abstractmethod
    def normalize(self, record: ParsedSourceRecord) -> NormalizedIngestionRecord:
        raise NotImplementedError
