from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Product, ProductSourceRecord, ProductVariant


@dataclass(slots=True)
class ExactMatchCandidate:
    product_id: UUID
    product_variant_id: UUID
    product_source_record_id: UUID | None
    brand: str | None
    gtin: str | None
    mpn: str | None
    asin: str | None
    pack_count: int | None
    quantity: Decimal | None
    quantity_unit: str | None
    weight: Decimal | None
    weight_unit: str | None
    volume: Decimal | None
    volume_unit: str | None
    size: str | None
    color: str | None
    material: str | None
    is_bundle: bool


@dataclass(slots=True)
class HybridMatchCandidate:
    product_id: UUID
    product_variant_id: UUID
    product_source_record_id: UUID | None
    normalized_name: str
    brand: str | None
    category: str | None
    source_title: str | None
    pack_count: int | None
    quantity: Decimal | None
    quantity_unit: str | None
    weight: Decimal | None
    weight_unit: str | None
    volume: Decimal | None
    volume_unit: str | None
    size: str | None
    color: str | None
    material: str | None
    is_bundle: bool


class ExactMatchRepository(Protocol):
    def find_by_gtin(self, db: Session, gtin: str) -> list[ExactMatchCandidate]:
        ...

    def find_by_asin(self, db: Session, asin: str) -> list[ExactMatchCandidate]:
        ...

    def find_by_mpn_brand(self, db: Session, mpn: str, brand: str) -> list[ExactMatchCandidate]:
        ...


class HybridMatchRepository(Protocol):
    def find_candidates(
        self,
        db: Session,
        *,
        brand: str | None,
        title_tokens: list[str],
        limit: int = 50,
    ) -> list[HybridMatchCandidate]:
        ...


class SQLAlchemyExactMatchRepository:
    def find_by_gtin(self, db: Session, gtin: str) -> list[ExactMatchCandidate]:
        stmt = self._base_candidate_query().where(ProductVariant.gtin == gtin)
        return self._load_candidates(db, stmt)

    def find_by_asin(self, db: Session, asin: str) -> list[ExactMatchCandidate]:
        stmt = self._base_candidate_query().where(
            ProductSourceRecord.source_attributes["asin"].astext == asin
        )
        return self._load_candidates(db, stmt)

    def find_by_mpn_brand(self, db: Session, mpn: str, brand: str) -> list[ExactMatchCandidate]:
        stmt = self._base_candidate_query().where(
            ProductVariant.mpn == mpn,
            func.lower(Product.brand) == brand.casefold(),
        )
        return self._load_candidates(db, stmt)

    def _base_candidate_query(self) -> Select:
        return (
            select(
                Product.id.label("product_id"),
                ProductVariant.id.label("product_variant_id"),
                ProductSourceRecord.id.label("product_source_record_id"),
                Product.brand.label("brand"),
                ProductVariant.gtin.label("gtin"),
                ProductVariant.mpn.label("mpn"),
                ProductSourceRecord.source_attributes["asin"].astext.label("asin"),
                ProductVariant.pack_count.label("pack_count"),
                ProductVariant.quantity.label("quantity"),
                ProductVariant.quantity_unit.label("quantity_unit"),
                ProductVariant.weight.label("weight"),
                ProductVariant.weight_unit.label("weight_unit"),
                ProductVariant.volume.label("volume"),
                ProductVariant.volume_unit.label("volume_unit"),
                ProductVariant.size.label("size"),
                ProductVariant.color.label("color"),
                ProductVariant.material.label("material"),
                ProductVariant.is_bundle.label("is_bundle"),
            )
            .select_from(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .outerjoin(ProductSourceRecord, ProductSourceRecord.product_variant_id == ProductVariant.id)
        )

    def _load_candidates(self, db: Session, stmt: Select) -> list[ExactMatchCandidate]:
        rows = db.execute(stmt).mappings().all()
        return [
            ExactMatchCandidate(
                product_id=row["product_id"],
                product_variant_id=row["product_variant_id"],
                product_source_record_id=row["product_source_record_id"],
                brand=row["brand"],
                gtin=row["gtin"],
                mpn=row["mpn"],
                asin=row["asin"],
                pack_count=row["pack_count"],
                quantity=row["quantity"],
                quantity_unit=row["quantity_unit"],
                weight=row["weight"],
                weight_unit=row["weight_unit"],
                volume=row["volume"],
                volume_unit=row["volume_unit"],
                size=row["size"],
                color=row["color"],
                material=row["material"],
                is_bundle=row["is_bundle"],
            )
            for row in rows
        ]


class SQLAlchemyHybridMatchRepository:
    def find_candidates(
        self,
        db: Session,
        *,
        brand: str | None,
        title_tokens: list[str],
        limit: int = 50,
    ) -> list[HybridMatchCandidate]:
        comparable_tokens = [token.casefold() for token in title_tokens if len(token) >= 3][:6]
        if brand is None and len(comparable_tokens) < 2:
            return []

        stmt = self._base_candidate_query()

        if brand:
            stmt = stmt.where(func.lower(Product.brand) == brand.casefold())

        title_conditions = [
            or_(
                func.lower(Product.normalized_name).contains(token),
                func.lower(func.coalesce(ProductSourceRecord.source_title, "")).contains(token),
            )
            for token in comparable_tokens
        ]
        if title_conditions:
            stmt = stmt.where(and_(*title_conditions[:2]) if brand is None else or_(*title_conditions))

        stmt = stmt.order_by(Product.updated_at.desc(), ProductVariant.updated_at.desc(), ProductVariant.id.asc()).limit(
            limit
        )
        return self._load_candidates(db, stmt)

    def _base_candidate_query(self) -> Select:
        return (
            select(
                Product.id.label("product_id"),
                ProductVariant.id.label("product_variant_id"),
                ProductSourceRecord.id.label("product_source_record_id"),
                Product.normalized_name.label("normalized_name"),
                Product.brand.label("brand"),
                Product.category.label("category"),
                ProductSourceRecord.source_title.label("source_title"),
                ProductVariant.pack_count.label("pack_count"),
                ProductVariant.quantity.label("quantity"),
                ProductVariant.quantity_unit.label("quantity_unit"),
                ProductVariant.weight.label("weight"),
                ProductVariant.weight_unit.label("weight_unit"),
                ProductVariant.volume.label("volume"),
                ProductVariant.volume_unit.label("volume_unit"),
                ProductVariant.size.label("size"),
                ProductVariant.color.label("color"),
                ProductVariant.material.label("material"),
                ProductVariant.is_bundle.label("is_bundle"),
            )
            .select_from(ProductVariant)
            .join(Product, Product.id == ProductVariant.product_id)
            .outerjoin(ProductSourceRecord, ProductSourceRecord.product_variant_id == ProductVariant.id)
        )

    def _load_candidates(self, db: Session, stmt: Select) -> list[HybridMatchCandidate]:
        rows = db.execute(stmt).mappings().all()
        candidates_by_variant_id: dict[UUID, HybridMatchCandidate] = {}

        for row in rows:
            variant_id = row["product_variant_id"]
            existing = candidates_by_variant_id.get(variant_id)
            source_title = row["source_title"]

            if existing is None or (existing.source_title is None and source_title is not None):
                candidates_by_variant_id[variant_id] = HybridMatchCandidate(
                    product_id=row["product_id"],
                    product_variant_id=variant_id,
                    product_source_record_id=row["product_source_record_id"],
                    normalized_name=row["normalized_name"],
                    brand=row["brand"],
                    category=row["category"],
                    source_title=source_title,
                    pack_count=row["pack_count"],
                    quantity=row["quantity"],
                    quantity_unit=row["quantity_unit"],
                    weight=row["weight"],
                    weight_unit=row["weight_unit"],
                    volume=row["volume"],
                    volume_unit=row["volume_unit"],
                    size=row["size"],
                    color=row["color"],
                    material=row["material"],
                    is_bundle=row["is_bundle"],
                )

        return list(candidates_by_variant_id.values())
