# coding: utf-8

from typing import ClassVar, Dict, List, Tuple  # noqa: F401

from pydantic import Field, field_validator
from typing import Any, List, Optional
from typing_extensions import Annotated
from openapi_server.models.admin_categories_slug_patch_request import AdminCategoriesSlugPatchRequest
from openapi_server.models.admin_reports_report_id_patch_request import AdminReportsReportIdPatchRequest
from openapi_server.models.inline_object1 import InlineObject1
from openapi_server.models.product_admin import ProductAdmin
from openapi_server.models.report_admin import ReportAdmin
from openapi_server.security_api import get_token_adminAuth

class BaseAdminApi:
    subclasses: ClassVar[Tuple] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        BaseAdminApi.subclasses = BaseAdminApi.subclasses + (cls,)
    async def admin_products_get(
        self,
        active: Optional[bool],
        category: Optional[str],
        price_band: Optional[Annotated[int, Field(le=4, ge=1)]],
    ) -> List[ProductAdmin]:
        ...


    async def admin_products_post(
        self,
        product_admin: ProductAdmin,
    ) -> ProductAdmin:
        """Product images are imported and registered OUT OF BAND (the ingestion pipeline re-encodes, strips metadata and filenames, and writes the ProductImage row). This endpoint references an already-registered image by &#x60;imageStorageKey&#x60;, whose format is &#x60;products/{contentHash}.{webp|jpg}&#x60;. An unknown storage key is rejected. &#x60;snapshotDate&#x60; is a calendar date (date, not datetime) and matches the reveal copy (\&quot;snapshot price as of …\&quot;). &#x60;priceBand&#x60; is derived server-side from priceCents and is immutable — product price snapshots are immutable after curation; corrections create a new product version. """
        ...


    async def admin_categories_slug_patch(
        self,
        slug: str,
        admin_categories_slug_patch_request: AdminCategoriesSlugPatchRequest,
    ) -> None:
        ...


    async def admin_reports_get(
        self,
        status: Optional[str],
    ) -> List[ReportAdmin]:
        ...


    async def admin_reports_report_id_patch(
        self,
        reportId: int,
        admin_reports_report_id_patch_request: AdminReportsReportIdPatchRequest,
    ) -> None:
        ...
