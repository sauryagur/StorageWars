from __future__ import annotations

from datetime import datetime, time, timezone

from fastapi.responses import JSONResponse, Response
from sqlmodel import select

from openapi_server.apis.admin_api_base import BaseAdminApi
from openapi_server.impl import content
from openapi_server.impl.db import read, write
from openapi_server.impl.errors import ApiError, require_admin
from openapi_server.impl.tables import (
    Category,
    PriceBand,
    Product,
    ProductImage,
    Report,
    ReportStatus,
)
from openapi_server.impl.views import product_admin, report_admin
from openapi_server.models.admin_categories_slug_patch_request import (
    AdminCategoriesSlugPatchRequest,
)
from openapi_server.models.admin_reports_report_id_patch_request import (
    AdminReportsReportIdPatchRequest,
)
from openapi_server.models.product_admin import ProductAdmin


def _response(model, status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        model.model_dump(by_alias=True, exclude_unset=True, mode="json"),
        status_code=status_code,
    )


def _product_data(product, image: ProductImage, category: Category) -> dict:
    return {
        "id": product.id,
        "image_storage_key": image.storage_key,
        "original_title": product.original_title,
        "original_description": product.original_description,
        "price_cents": product.price_cents,
        "currency": product.currency,
        "category": category.slug,
        "star_rating": product.star_rating,
        "review_count": product.review_count,
        "snapshot_date": product.snapshot_date.date(),
        "price_band": product.price_band,
        "active": product.active,
    }


class AdminApiImpl(BaseAdminApi):
    async def admin_products_get(
        self, active: bool | None, category: str | None, price_band: int | None
    ) -> JSONResponse:
        require_admin()

        def fetch(session):
            query = (
                select(Product, Category, ProductImage)
                .join(Category, Product.category_id == Category.id)
                .join(ProductImage, Product.image_id == ProductImage.id)
            )
            if active is not None:
                query = query.where(Product.active == active)
            if category is not None:
                query = query.where(Category.slug == category)
            if price_band is not None:
                query = query.where(Product.price_band == PriceBand(price_band))
            return [
                product_admin(_product_data(product, image, row_category)).model_dump(
                    by_alias=True, exclude_unset=True, mode="json"
                )
                for product, row_category, image in session.exec(query).all()
            ]

        rows = await read(fetch)
        return JSONResponse(rows, status_code=200)

    async def admin_products_post(self, product_admin: ProductAdmin) -> JSONResponse:
        require_admin()
        if product_admin.currency != "USD":
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "currency must be USD",
                field_errors=[
                    {
                        "field": "currency",
                        "rule": "VALIDATION_FAILED",
                        "message": "currency must be USD",
                    }
                ],
            )

        def create(session):
            image = session.exec(
                select(ProductImage).where(
                    ProductImage.storage_key == product_admin.image_storage_key
                )
            ).first()
            if image is None:
                return None, None
            category = session.exec(
                select(Category).where(
                    Category.slug == product_admin.category, Category.active.is_(True)
                )
            ).first()
            if category is None:
                return "category", None
            row = Product(
                image_id=image.id,
                original_title=product_admin.original_title,
                original_description=product_admin.original_description,
                price_cents=product_admin.price_cents,
                currency="USD",
                category_id=category.id,
                star_rating=product_admin.star_rating,
                review_count=product_admin.review_count,
                snapshot_date=datetime.combine(
                    product_admin.snapshot_date, time.min, tzinfo=timezone.utc
                ),
                price_band=Product.compute_band(product_admin.price_cents),
                active=True if product_admin.active is None else product_admin.active,
            )
            session.add(row)
            session.flush()
            return "created", _product_data(row, image, category)

        state, product_data = await write(create)
        if state is None:
            raise ApiError(
                422, "IMAGE_KEY_UNKNOWN", "imageStorageKey is not registered"
            )
        if state == "category":
            raise ApiError(
                422,
                "VALIDATION_FAILED",
                "category must be active",
                field_errors=[
                    {
                        "field": "category",
                        "rule": "CATEGORY_UNKNOWN",
                        "message": "Unknown or inactive category",
                    }
                ],
            )
        return _response(product_admin(product_data), 201)

    async def admin_categories_slug_patch(
        self,
        slug: str,
        admin_categories_slug_patch_request: AdminCategoriesSlugPatchRequest,
    ) -> JSONResponse:
        require_admin()
        updates = admin_categories_slug_patch_request.model_dump(exclude_unset=True)
        if not updates:
            raise ApiError(
                422, "VALIDATION_FAILED", "At least one category field is required"
            )

        def patch(session):
            category = session.exec(
                select(Category).where(Category.slug == slug)
            ).first()
            if category is None:
                return False
            for field, value in updates.items():
                setattr(category, field, value)
            session.add(category)
            return True

        if not await write(patch):
            raise ApiError(404, "NOT_FOUND", "Category not found")
        categories = await content.load_categories()
        updated = next((item for item in categories if item.slug == slug), None)
        if updated is not None:
            from openapi_server.impl.engine.registry import registry

            for room in registry.rooms.values():
                for card in room.cards.values():
                    product_category = getattr(card.product, "category", None)
                    if product_category is not None and product_category.slug == slug:
                        product_category.sigma = updated.sigma
        return Response(status_code=200)

    async def admin_reports_get(self, status: str | None) -> JSONResponse:
        require_admin()
        status_value = None
        if status is not None:
            try:
                status_value = ReportStatus(status)
            except ValueError as exc:
                raise ApiError(
                    422, "VALIDATION_FAILED", "Invalid report status"
                ) from exc
        rows = await read(
            lambda session: list(
                session.exec(
                    select(Report).where(Report.status == status_value)
                    if status_value is not None
                    else select(Report)
                ).all()
            )
        )
        return JSONResponse(
            [
                report_admin(row).model_dump(
                    by_alias=True, exclude_unset=True, mode="json"
                )
                for row in rows
            ],
            status_code=200,
        )

    async def admin_reports_report_id_patch(
        self,
        reportId: int,
        admin_reports_report_id_patch_request: AdminReportsReportIdPatchRequest,
    ) -> JSONResponse:
        require_admin()
        try:
            new_status = ReportStatus(admin_reports_report_id_patch_request.status)
            if new_status == ReportStatus.OPEN:
                raise ValueError
        except ValueError as exc:
            raise ApiError(
                422, "VALIDATION_FAILED", "Report status must be RESOLVED or DISMISSED"
            ) from exc
        note_was_set = (
            "resolution_note" in admin_reports_report_id_patch_request.model_fields_set
        )
        note = admin_reports_report_id_patch_request.resolution_note

        def patch(session):
            report = session.get(Report, reportId)
            if report is None:
                return False
            report.status = new_status
            if note_was_set:
                report.resolution_note = note
            session.add(report)
            return True

        if not await write(patch):
            raise ApiError(404, "NOT_FOUND", "Report not found")
        return Response(status_code=200)
