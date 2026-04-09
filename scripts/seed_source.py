from __future__ import annotations

import json
import sys
from pathlib import Path

from sqlalchemy import select

from app.db.enums import SourceType
from app.db.models import Source
from app.db.session import SessionLocal


def main() -> int:
    data_file = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/seed_sources.json")
    payload = json.loads(data_file.read_text())
    sources = payload if isinstance(payload, list) else [payload]

    created = 0
    updated = 0

    with SessionLocal() as db:
        for item in sources:
            slug = item["slug"].strip()
            source = db.scalar(select(Source).where(Source.slug == slug))
            if source is None:
                source = Source(
                    name=item["name"].strip(),
                    slug=slug,
                    source_type=SourceType(item["source_type"]),
                    base_url=item.get("base_url"),
                    is_active=bool(item.get("is_active", True)),
                    config=item.get("config", {}),
                )
                db.add(source)
                created += 1
            else:
                source.name = item["name"].strip()
                source.source_type = SourceType(item["source_type"])
                source.base_url = item.get("base_url")
                source.is_active = bool(item.get("is_active", True))
                source.config = item.get("config", {})
                updated += 1

        db.commit()

    print(json.dumps({"created": created, "updated": updated, "source_count": len(sources)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
