from __future__ import annotations

import argparse
import base64
import hashlib
import io
import logging
import re
import yaml
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse
from urllib.request import urlopen

from sqlmodel import SQLModel, Session, select

from openapi_server.impl.config import settings
from openapi_server.impl.db import engine, session_scope
from openapi_server.impl.storage import Storage, StorageError, get_storage
from openapi_server.impl.tables import Category, Product, ProductImage

logger = logging.getLogger(__name__)
_PRICE_MIN_CENTS = 200
_PRICE_MAX_CENTS = 50_000
# A standards-compliant 1x1 RGB PNG. Fixtures intentionally need no Pillow.
_FIXTURE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8A"
    "AwMCAO+jXioAAAAASUVORK5CYII="
)
_FIXTURE_CATEGORIES = (
    ("home-kitchen", "Home & Kitchen"),
    ("electronics", "Electronics"),
    ("beauty", "Beauty & Personal Care"),
    ("sports-outdoors", "Sports & Outdoors"),
    ("toys-games", "Toys & Games"),
    ("clothing", "Clothing & Accessories"),
    ("tools", "Tools & Home Improvement"),
    ("office", "Office Products"),
    ("garden", "Garden & Patio"),
    ("pets", "Pet Supplies"),
    ("automotive", "Automotive"),
    ("food", "Grocery & Gourmet Food"),
)


def _read_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as stream:
        config = yaml.safe_load(stream)
    if not isinstance(config, dict):
        raise ValueError(f"Ingest config must contain a YAML mapping: {path}")
    return config


def _mapped_value(
    row: Mapping[str, Any], column: Any, *, required: bool = False
) -> Any:
    if not column:
        if required:
            raise ValueError("Required ingest column mapping is blank")
        return None
    try:
        value = row[column]
    except (KeyError, TypeError):
        if required:
            raise ValueError(
                f"Dataset row is missing mapped column {column!r}"
            ) from None
        return None
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return "; ".join(_text(part) for part in value if part is not None).strip()
    return str(value).strip()


def _price_cents(value: Any, unit: str, multiplier: Any) -> int:
    if value is None or isinstance(value, bool):
        raise ValueError("price is empty or not numeric")
    if isinstance(value, Mapping):
        value = value.get("amount", value.get("value"))
    if isinstance(value, str):
        value = re.sub(r"[,$€£¥₹\s]", "", value)
    try:
        amount = Decimal(str(value)) * Decimal(str(multiplier))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"invalid price {value!r}") from None
    normalized_unit = (unit or "dollars").lower()
    if normalized_unit in ("cent", "cents"):
        cents = amount
    elif normalized_unit in ("dollar", "dollars", "usd"):
        cents = amount * 100
    else:
        raise ValueError(f"unsupported price_unit {unit!r}; use dollars or cents")
    return int(cents.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _snapshot_date(value: Any) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(value, tz=timezone.utc)
    else:
        text = str(value).strip()
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _image_bytes(value: Any) -> bytes:
    if isinstance(value, (list, tuple)):
        candidates = []
        for item in value:
            if isinstance(item, Mapping):
                candidates.extend(item.get(key) for key in ("hi_res", "large", "thumb"))
            else:
                candidates.append(item)
        value = next((candidate for candidate in candidates if candidate), None)
    if isinstance(value, Mapping):
        data = value.get("bytes")
        if data:
            return bytes(data)
        path = value.get("path")
        if path:
            value = path
        else:
            candidates = []
            for key in ("hi_res", "large", "thumb"):
                variant = value.get(key)
                if isinstance(variant, (list, tuple)):
                    candidates.extend(variant)
                elif variant:
                    candidates.append(variant)
            value = next((candidate for candidate in candidates if candidate), None)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    if isinstance(value, str):
        source = value.strip()
        if source.startswith("data:"):
            header, encoded = source.split(",", 1)
            if ";base64" not in header:
                raise ValueError("image data URL must use base64 encoding")
            return base64.b64decode(encoded, validate=True)
        if urlparse(source).scheme in ("http", "https"):
            with urlopen(source, timeout=20) as response:
                return response.read()
        if source:
            return Path(source).read_bytes()
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None and isinstance(value, Image.Image):
        buffer = io.BytesIO()
        value.save(buffer, format="PNG")
        return buffer.getvalue()
    raise ValueError("image value has no bytes, path, or URL")


def _ingest(config: Mapping[str, Any], storage: Storage) -> tuple[int, int]:
    source = config.get("dataset", {}) or {}
    dataset_id = source.get("name")
    split = source.get("split")
    if not dataset_id or not split:
        raise ValueError(
            "ingest.yaml must set dataset.name and dataset.split before normal "
            "ingestion"
        )
    mapping = config.get("columns", {}) or {}
    required = ("title", "price", "image")
    missing = [name for name in required if not mapping.get(name)]
    if missing:
        raise ValueError(
            f"ingest.yaml has blank required column mapping(s): {', '.join(missing)}"
        )
    max_rows = source.get("max_rows")
    if max_rows is not None and int(max_rows) < 1:
        raise ValueError("dataset.max_rows must be a positive integer")
    from datasets import load_dataset

    if source.get("format") == "parquet":
        data_files = source.get("data_files")
        if not data_files:
            raise ValueError("dataset.data_files is required for Parquet input")
        dataset = load_dataset(
            "parquet",
            data_files=data_files,
            split=split,
            streaming=bool(source.get("streaming", False)),
        )
    else:
        dataset = load_dataset(
            dataset_id,
            name=source.get("config_name") or None,
            split=split,
            revision=source.get("revision") or None,
            streaming=bool(source.get("streaming", False)),
        )
    inserted = skipped = 0
    with session_scope() as session:
        for index, row in enumerate(dataset):
            if max_rows is not None and index >= int(max_rows):
                break
            try:
                if _ingest_record(session, row, mapping, config, storage):
                    inserted += 1
                else:
                    skipped += 1
            except (ValueError, TypeError, OSError, StorageError, InvalidOperation) as exc:
                skipped += 1
                logger.warning("Skipping dataset row %d: %s", index, exc)
    return inserted, skipped


def _webp(image_value: Any) -> tuple[bytes, int, int]:
    from PIL import Image, UnidentifiedImageError

    raw = _image_bytes(image_value)
    try:
        with Image.open(io.BytesIO(raw)) as opened:
            opened.load()
            image = opened.convert("RGBA" if "A" in opened.getbands() else "RGB")
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise ValueError(f"image cannot be decoded: {exc}") from None
    output = io.BytesIO()
    image.save(output, format="WEBP", quality=85, method=6)
    return output.getvalue(), image.width, image.height


def _category_slug(label: str, category_map: Mapping[str, Any]) -> str:
    mapped = category_map.get(label)
    if mapped is not None:
        if isinstance(mapped, Mapping):
            mapped = mapped.get("slug")
        if mapped:
            return str(mapped).strip().lower()
    return re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:32]


def _ensure_category(session: Session, slug: str, display_name: str) -> Category:
    category = session.exec(select(Category).where(Category.slug == slug)).first()
    if category is None:
        category = Category(
            slug=slug, display_name=display_name[:64], sigma=0.5, active=True
        )
        session.add(category)
        session.flush()
    return category


def _stored_image(session: Session, content_hash: str) -> ProductImage | None:
    return session.exec(
        select(ProductImage).where(ProductImage.content_hash == content_hash)
    ).first()


def _ingest_record(
    session: Session,
    row: Mapping[str, Any],
    mapping: Mapping[str, Any],
    config: Mapping[str, Any],
    storage: Storage,
) -> bool:
    title = _text(_mapped_value(row, mapping.get("title"), required=True))
    description = _text(_mapped_value(row, mapping.get("description")))
    if not title:
        raise ValueError("title is empty")
    cents = _price_cents(
        _mapped_value(row, mapping.get("price"), required=True),
        str(config.get("price_unit", "dollars")),
        config.get("price_multiplier", 1),
    )
    if not (_PRICE_MIN_CENTS <= cents <= _PRICE_MAX_CENTS):
        return False

    image_bytes, width, height = _webp(
        _mapped_value(row, mapping.get("image"), required=True)
    )
    content_hash = hashlib.sha256(image_bytes).hexdigest()
    product_image = _stored_image(session, content_hash)
    if product_image is not None:
        # Reject near-duplicate image content; this also makes reruns idempotent.
        if session.exec(
            select(Product).where(Product.image_id == product_image.id)
        ).first():
            return False
    else:
        storage_key = f"products/{content_hash}.webp"
        existing = session.exec(
            select(ProductImage).where(ProductImage.storage_key == storage_key)
        ).first()
        if existing is not None:
            product_image = existing
            if session.exec(
                select(Product).where(Product.image_id == product_image.id)
            ).first():
                return False
        else:
            storage.put(storage_key, image_bytes)
            product_image = ProductImage(
                storage_key=storage_key,
                content_hash=content_hash,
                width=width,
                height=height,
                bytes_size=len(image_bytes),
            )
            session.add(product_image)
            session.flush()
    category_value = _text(_mapped_value(row, mapping.get("category")))
    category_map = config.get("category_map", {}) or {}
    if category_value:
        slug = _category_slug(category_value, category_map)
        mapped = category_map.get(category_value)
        display_name = (
            mapped.get("display_name", category_value)
            if isinstance(mapped, Mapping)
            else category_value
        )
    else:
        default_slug = config.get("default_category_slug")
        if not default_slug:
            raise ValueError(
                "row has no category and default_category_slug is not configured"
            )
        slug = str(default_slug).lower()
        display_name = slug.replace("-", " ").title()
    category = _ensure_category(session, slug, str(display_name))

    existing_product = session.exec(
        select(Product).where(
            Product.image_id == product_image.id,
            Product.price_cents == cents,
            Product.original_title == title,
        )
    ).first()
    if existing_product is not None:
        return False
    rating_value = _mapped_value(row, mapping.get("rating"))
    review_value = _mapped_value(row, mapping.get("review_count"))
    rating = float(rating_value) if rating_value not in (None, "") else None
    reviews = int(review_value) if review_value not in (None, "") else None
    snapshot_value = _mapped_value(row, mapping.get("snapshot_date"))
    product = Product(
        image_id=product_image.id,
        original_title=title[:512],
        original_description=description[:4096],
        price_cents=cents,
        currency="USD",
        category_id=category.id,
        star_rating=rating,
        review_count=reviews,
        snapshot_date=_snapshot_date(snapshot_value),
        price_band=Product.compute_band(cents),
        active=True,
    )
    session.add(product)
    return True


def _seed_fixtures_sync() -> tuple[int, int]:
    storage = get_storage(settings)
    image_hash = hashlib.sha256(_FIXTURE_PNG).hexdigest()
    storage_key = f"products/{image_hash}.png"
    with session_scope() as session:
        categories = {}
        for slug, display_name in _FIXTURE_CATEGORIES:
            categories[slug] = _ensure_category(session, slug, display_name)
        image = session.exec(
            select(ProductImage).where(ProductImage.storage_key == storage_key)
        ).first()
        if image is None:
            storage.put(storage_key, _FIXTURE_PNG)
            image = ProductImage(
                storage_key=storage_key,
                content_hash=image_hash,
                width=1,
                height=1,
                bytes_size=len(_FIXTURE_PNG),
            )
            session.add(image)
            session.flush()
        inserted = 0
        for index in range(24):
            title = f"Fixture Product {index + 1:02d}"
            price = 250 + index * 1_975
            existing = session.exec(
                select(Product).where(Product.original_title == title)
            ).first()
            if existing is not None:
                continue
            category = categories[
                _FIXTURE_CATEGORIES[index % len(_FIXTURE_CATEGORIES)][0]
            ]
            session.add(
                Product(
                    image_id=image.id,
                    original_title=title,
                    original_description=(
                        f"Deterministic development fixture item {index + 1:02d}."
                    ),
                    price_cents=price,
                    currency="USD",
                    category_id=category.id,
                    star_rating=round(3.0 + (index % 5) * 0.5, 1),
                    review_count=index * 137,
                    snapshot_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
                    price_band=Product.compute_band(price),
                    active=True,
                )
            )
            inserted += 1
    return inserted, 24 - inserted


async def seed_fixtures() -> tuple[int, int]:
    """Idempotently seed the fixture catalog without blocking the event loop."""
    from fastapi.concurrency import run_in_threadpool

    return await run_in_threadpool(_seed_fixtures_sync)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ingest product content or seed deterministic fixtures"
    )
    parser.add_argument(
        "--config",
        default="ingest.yaml",
        help="YAML ingest configuration (default: ingest.yaml)",
    )
    parser.add_argument(
        "--fixtures",
        action="store_true",
        help="Seed 12 categories and 24 deterministic development products",
    )
    args = parser.parse_args(argv)
    SQLModel.metadata.create_all(engine)
    if args.fixtures:
        inserted, skipped = _seed_fixtures_sync()
        logger.info(
            "Fixture seed complete: %d products inserted, %d already present",
            inserted,
            skipped,
        )
        return 0
    config = _read_config(Path(args.config))
    inserted, skipped = _ingest(config, get_storage(settings))
    logger.info("Ingest complete: %d products inserted, %d skipped", inserted, skipped)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
