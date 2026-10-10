# coding: utf-8

from fastapi.testclient import TestClient


from pydantic import Field, field_validator  # noqa: F401
from typing import Any, List, Optional  # noqa: F401
from typing_extensions import Annotated  # noqa: F401
from openapi_server.models.admin_categories_slug_patch_request import AdminCategoriesSlugPatchRequest  # noqa: F401
from openapi_server.models.admin_reports_report_id_patch_request import AdminReportsReportIdPatchRequest  # noqa: F401
from openapi_server.models.inline_object1 import InlineObject1  # noqa: F401
from openapi_server.models.product_admin import ProductAdmin  # noqa: F401
from openapi_server.models.report_admin import ReportAdmin  # noqa: F401


def test_admin_products_get(client: TestClient):
    """Test case for admin_products_get

    List products (full secrets)
    """
    params = [("active", True),     ("category", 'category_example'),     ("price_band", 56)]
    headers = {
        "Authorization": "Bearer special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/admin/products",
    #    headers=headers,
    #    params=params,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_admin_products_post(client: TestClient):
    """Test case for admin_products_post

    Create a product
    """
    product_admin = openapi_server.ProductAdmin()

    headers = {
        "Authorization": "Bearer special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "POST",
    #    "/admin/products",
    #    headers=headers,
    #    json=product_admin,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_admin_categories_slug_patch(client: TestClient):
    """Test case for admin_categories_slug_patch

    Tune a category (sigma)
    """
    admin_categories_slug_patch_request = openapi_server.AdminCategoriesSlugPatchRequest()

    headers = {
        "Authorization": "Bearer special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "PATCH",
    #    "/admin/categories/{slug}".format(slug='slug_example'),
    #    headers=headers,
    #    json=admin_categories_slug_patch_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_admin_reports_get(client: TestClient):
    """Test case for admin_reports_get

    List reports for review
    """
    params = [("status", 'status_example')]
    headers = {
        "Authorization": "Bearer special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "GET",
    #    "/admin/reports",
    #    headers=headers,
    #    params=params,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200


def test_admin_reports_report_id_patch(client: TestClient):
    """Test case for admin_reports_report_id_patch

    Resolve or dismiss a report
    """
    admin_reports_report_id_patch_request = openapi_server.AdminReportsReportIdPatchRequest()

    headers = {
        "Authorization": "Bearer special-key",
    }
    # uncomment below to make a request
    #response = client.request(
    #    "PATCH",
    #    "/admin/reports/{reportId}".format(reportId=56),
    #    headers=headers,
    #    json=admin_reports_report_id_patch_request,
    #)

    # uncomment below to assert the status code of the HTTP response
    #assert response.status_code == 200

