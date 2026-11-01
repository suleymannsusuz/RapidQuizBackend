from unittest import mock

import pytest
from rest_framework import exceptions

from apps.catalog.models import Category
from apps.core.exceptions import APIError, api_exception_handler

pytestmark = pytest.mark.django_db


def test_categories_returns_only_active_in_sort_order(api_client):
    Category.objects.create(slug="b", name="B", color="#111111", sort_order=2)
    Category.objects.create(slug="a", name="A", color="#222222", sort_order=1)
    Category.objects.create(slug="gizli", name="Gizli", color="#333333", is_active=False)

    response = api_client.get("/api/v1/categories/")

    assert response.status_code == 200
    assert [c["slug"] for c in response.json()] == ["a", "b"]
    assert set(response.json()[0]) == {"slug", "name", "description", "color", "icon"}


def test_categories_need_no_authentication_or_cookies(api_client):
    response = api_client.get("/api/v1/categories/")
    assert response.status_code == 200
    assert not response.cookies


def test_health_ok(api_client):
    response = api_client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_reports_unavailable_database(api_client):
    with mock.patch("apps.core.views.connection.cursor", side_effect=Exception("db down")):
        response = api_client.get("/api/v1/health/")
    assert response.status_code == 503
    assert response.json()["database"] == "unavailable"


def test_openapi_schema_and_docs_are_served(api_client):
    schema = api_client.get("/api/v1/schema/")
    assert schema.status_code == 200
    assert b"/api/v1/categories/" in schema.content
    assert b"/api/v1/health/" in schema.content
    assert api_client.get("/api/v1/docs/").status_code == 200


def test_unknown_api_path_returns_json_error(api_client):
    response = api_client.get("/api/v1/yok/")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_method_not_allowed_uses_error_format(api_client):
    response = api_client.post("/api/v1/categories/", {}, format="json")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"
    assert set(response.json()["error"]) == {"code", "message", "details"}


def test_validation_error_exposes_field_details():
    exc = exceptions.ValidationError({"player_name": ["Çok kısa."]})
    response = api_exception_handler(exc, {})
    assert response.status_code == 400
    assert response.data["error"]["code"] == "validation_error"
    assert response.data["error"]["details"] == {"player_name": ["Çok kısa."]}


def test_list_validation_error_goes_to_non_field_errors():
    response = api_exception_handler(exceptions.ValidationError(["Hatalı."]), {})
    assert response.data["error"]["details"] == {"non_field_errors": ["Hatalı."]}


def test_throttled_maps_to_rate_limited_with_retry_after():
    response = api_exception_handler(exceptions.Throttled(wait=12), {})
    assert response.status_code == 429
    assert response.data["error"]["code"] == "rate_limited"
    assert response.data["error"]["details"] == {"retry_after_seconds": 12}


def test_api_error_carries_code_status_and_message():
    exc = APIError("session_expired", "Oturum süresi doldu.", status_code=410)
    response = api_exception_handler(exc, {})
    assert response.status_code == 410
    assert response.data == {
        "error": {"code": "session_expired", "message": "Oturum süresi doldu.", "details": {}}
    }


def test_unauthenticated_maps_to_invalid_token():
    response = api_exception_handler(exceptions.NotAuthenticated(), {})
    assert response.status_code == 401
    assert response.data["error"]["code"] == "invalid_token"
