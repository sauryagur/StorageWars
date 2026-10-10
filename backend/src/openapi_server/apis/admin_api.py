# coding: utf-8

from typing import Dict, List  # noqa: F401
import importlib
import pkgutil

from openapi_server.apis.admin_api_base import BaseAdminApi
import openapi_server.impl

from fastapi import (  # noqa: F401
    APIRouter,
    Body,
    Cookie,
    Depends,
    Form,
    Header,
    HTTPException,
    Path,
    Query,
    Response,
    Security,
    status,
)

from pydantic import Field, field_validator
from typing import Any, List, Optional
from typing_extensions import Annotated
from openapi_server.models.admin_categories_slug_patch_request import AdminCategoriesSlugPatchRequest
from openapi_server.models.admin_reports_report_id_patch_request import AdminReportsReportIdPatchRequest
from openapi_server.models.inline_object1 import InlineObject1
from openapi_server.models.product_admin import ProductAdmin
from openapi_server.models.report_admin import ReportAdmin
from openapi_server.models.extra_models import TokenModel  # noqa: F401
from openapi_server.security_api import get_token_adminAuth

router = APIRouter()

ns_pkg = openapi_server.impl
for _, name, _ in pkgutil.iter_modules(ns_pkg.__path__, ns_pkg.__name__ + "."):
    importlib.import_module(name)


@router.get(
    "/admin/products",
    responses={
        200: {"model": List[ProductAdmin], "description": "Products."},
        401: {"description": "Missing or invalid admin credential. Player session tokens are never accepted on admin endpoints; the error body is generic and reveals nothing about product data. "},
    },
    tags=["Admin"],
    summary="List products (full secrets)",
    response_model_by_alias=True,
)
async def admin_products_get(
    active: Optional[bool] = Query(None, description="", alias="active"),
    category: Optional[str] = Query(None, description="", alias="category"),
    price_band: Optional[Annotated[int, Field(le=4, ge=1)]] = Query(None, description="", alias="priceBand", ge=1, le=4),
    token_adminAuth: TokenModel = Security(
        get_token_adminAuth
    ),
) -> List[ProductAdmin]:
    if not BaseAdminApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAdminApi.subclasses[0]().admin_products_get(active, category, price_band)


@router.post(
    "/admin/products",
    responses={
        201: {"model": ProductAdmin, "description": "Created."},
        401: {"description": "Missing or invalid admin credential. Player session tokens are never accepted on admin endpoints; the error body is generic and reveals nothing about product data. "},
        422: {"model": InlineObject1, "description": "Input validation failure."},
    },
    tags=["Admin"],
    summary="Create a product",
    response_model_by_alias=True,
)
async def admin_products_post(
    product_admin: ProductAdmin = Body(..., description=""),
    token_adminAuth: TokenModel = Security(
        get_token_adminAuth
    ),
) -> ProductAdmin:
    """Product images are imported and registered OUT OF BAND (the ingestion pipeline re-encodes, strips metadata and filenames, and writes the ProductImage row). This endpoint references an already-registered image by &#x60;imageStorageKey&#x60;, whose format is &#x60;products/{contentHash}.{webp|jpg}&#x60;. An unknown storage key is rejected. &#x60;snapshotDate&#x60; is a calendar date (date, not datetime) and matches the reveal copy (\&quot;snapshot price as of …\&quot;). &#x60;priceBand&#x60; is derived server-side from priceCents and is immutable — product price snapshots are immutable after curation; corrections create a new product version. """
    if not BaseAdminApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAdminApi.subclasses[0]().admin_products_post(product_admin)


@router.patch(
    "/admin/categories/{slug}",
    responses={
        200: {"description": "Updated."},
        401: {"description": "Missing or invalid admin credential. Player session tokens are never accepted on admin endpoints; the error body is generic and reveals nothing about product data. "},
    },
    tags=["Admin"],
    summary="Tune a category (sigma)",
    response_model_by_alias=True,
)
async def admin_categories_slug_patch(
    slug: str = Path(..., description=""),
    admin_categories_slug_patch_request: AdminCategoriesSlugPatchRequest = Body(..., description=""),
    token_adminAuth: TokenModel = Security(
        get_token_adminAuth
    ),
) -> None:
    if not BaseAdminApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAdminApi.subclasses[0]().admin_categories_slug_patch(slug, admin_categories_slug_patch_request)


@router.get(
    "/admin/reports",
    responses={
        200: {"model": List[ReportAdmin], "description": "Reports."},
        401: {"description": "Missing or invalid admin credential. Player session tokens are never accepted on admin endpoints; the error body is generic and reveals nothing about product data. "},
    },
    tags=["Admin"],
    summary="List reports for review",
    response_model_by_alias=True,
)
async def admin_reports_get(
    status: Optional[str] = Query(None, description="", alias="status"),
    token_adminAuth: TokenModel = Security(
        get_token_adminAuth
    ),
) -> List[ReportAdmin]:
    if not BaseAdminApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAdminApi.subclasses[0]().admin_reports_get(status)


@router.patch(
    "/admin/reports/{reportId}",
    responses={
        200: {"description": "Updated."},
        401: {"description": "Missing or invalid admin credential. Player session tokens are never accepted on admin endpoints; the error body is generic and reveals nothing about product data. "},
    },
    tags=["Admin"],
    summary="Resolve or dismiss a report",
    response_model_by_alias=True,
)
async def admin_reports_report_id_patch(
    reportId: int = Path(..., description=""),
    admin_reports_report_id_patch_request: AdminReportsReportIdPatchRequest = Body(..., description=""),
    token_adminAuth: TokenModel = Security(
        get_token_adminAuth
    ),
) -> None:
    if not BaseAdminApi.subclasses:
        raise HTTPException(status_code=500, detail="Not implemented")
    return await BaseAdminApi.subclasses[0]().admin_reports_report_id_patch(reportId, admin_reports_report_id_patch_request)
