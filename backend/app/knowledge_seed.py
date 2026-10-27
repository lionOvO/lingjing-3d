"""Idempotently seed verified Blender modifier knowledge into MySQL and Milvus."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from sqlalchemy import select

from .agents import deterministic_embedding
from .database import SessionLocal, close_database, create_schema
from .milvus_schema import ensure_collections
from .models import RagEntryType, RagKnowledgeEntry

logger = logging.getLogger("digital_human.knowledge_seed")
SEED_FILE = Path(__file__).with_name("knowledge_data") / "blender_modifier_rules.json"
COLLECTION_DIMENSIONS = {
    "character_style_collection": 1024,
    "generation_params_collection": 768,
    "material_reference_collection": 512,
}


def load_seed_records(path: Path = SEED_FILE) -> list[dict[str, Any]]:
    records = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(records, list) or not records:
        raise ValueError(f"Knowledge seed must be a non-empty list: {path}")
    required = {"seed_key", "entry_type", "collection_name", "title", "content", "tags", "source", "best_params"}
    for record in records:
        if not isinstance(record, dict) or not required.issubset(record):
            raise ValueError(f"Invalid knowledge seed record: {record!r}")
        if record["collection_name"] not in COLLECTION_DIMENSIONS:
            raise ValueError(f"Unsupported collection: {record['collection_name']}")
    return records


def _record_text(record: dict[str, Any]) -> str:
    return " | ".join([
        str(record["title"]),
        str(record["content"]),
        " ".join(str(tag) for tag in record.get("tags", [])),
        json.dumps(record["best_params"], ensure_ascii=False, sort_keys=True),
    ])


def build_milvus_row(record: dict[str, Any]) -> dict[str, Any]:
    collection = record["collection_name"]
    params = json.dumps(record["best_params"], ensure_ascii=False, separators=(",", ":"))
    tags = list(record.get("tags", [])) + [f"seed_key={record['seed_key']}"]
    vector = deterministic_embedding(_record_text(record), COLLECTION_DIMENSIONS[collection])
    now = int(time.time())
    if collection == "character_style_collection":
        return {
            "style_embedding": vector,
            "style_name": record["title"],
            "tags": json.dumps(tags, ensure_ascii=False),
            "generation_params": params,
            "reference_image_url": "",
            "created_at": now,
        }
    if collection == "generation_params_collection":
        return {
            "param_embedding": vector,
            "object_type": record.get("object_type", "anime_character"),
            "model_type": record.get("model_type", "blender_modifier_policy"),
            "best_params": params,
            "success_rate": 0.0,
            "avg_quality_score": 0.0,
        }
    return {
        "material_embedding": vector,
        "material_type": record.get("material_type", "unknown"),
        "pbr_params": params,
        "preview_url": "",
    }


def _primary_key(result: Any) -> str:
    if isinstance(result, dict):
        values = result.get("primary_keys") or result.get("ids") or []
        if isinstance(values, (list, tuple)) and values:
            return str(values[0])
        if values:
            return str(values)
    values = getattr(result, "primary_keys", None) or getattr(result, "ids", None) or []
    if isinstance(values, (list, tuple)) and values:
        return str(values[0])
    if values:
        return str(values)
    raise RuntimeError(f"Milvus insert did not return a primary key: {result!r}")


async def seed_records(*, skip_milvus: bool = False) -> tuple[int, int]:
    records = load_seed_records()
    milvus = None
    if not skip_milvus:
        await asyncio.to_thread(ensure_collections)
        from pymilvus import MilvusClient

        from .config import settings

        milvus = MilvusClient(uri=f"http://{settings.milvus_host}:{settings.milvus_port}")

    created = 0
    skipped = 0
    async with SessionLocal() as db:
        for record in records:
            existing = await db.scalar(select(RagKnowledgeEntry).where(
                RagKnowledgeEntry.title == record["title"],
                RagKnowledgeEntry.source == record["source"],
            ))
            if existing:
                skipped += 1
                continue

            if milvus is not None:
                result = await asyncio.to_thread(
                    milvus.insert,
                    collection_name=record["collection_name"],
                    data=[build_milvus_row(record)],
                )
                milvus_id = _primary_key(result)
            else:
                milvus_id = f"seed:{record['seed_key']}"

            db.add(RagKnowledgeEntry(
                collection_name=record["collection_name"],
                milvus_id=milvus_id,
                entry_type=RagEntryType(record["entry_type"]),
                title=record["title"],
                content=record["content"],
                tags=record["tags"] + [f"seed_key={record['seed_key']}"],
                source=record["source"],
                avg_quality_score=None,
            ))
            await db.commit()
            created += 1
            logger.info("Seeded knowledge title=%s collection=%s milvus_id=%s", record["title"], record["collection_name"], milvus_id)
    return created, skipped


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed verified Blender modifier knowledge")
    parser.add_argument("--skip-milvus", action="store_true", help="Only seed MySQL; useful when Milvus is unavailable")
    args = parser.parse_args()
    try:
        await create_schema()
        created, skipped = await seed_records(skip_milvus=args.skip_milvus)
        print(json.dumps({"created": created, "skipped": skipped, "source": str(SEED_FILE)}, ensure_ascii=False))
    finally:
        await close_database()


if __name__ == "__main__":
    asyncio.run(main())
