import logging

from django.db import connection
from django.http import JsonResponse
from django.views.defaults import page_not_found, server_error
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .exceptions import error_body

logger = logging.getLogger(__name__)


class HealthSerializer(serializers.Serializer):
    status = serializers.CharField()
    database = serializers.CharField()


class HealthView(APIView):
    """Deploy ve izleme için sağlık kontrolü (veritabanı bağlantısını da dener)."""

    authentication_classes: list = []
    permission_classes: list = []

    @extend_schema(
        responses={
            200: HealthSerializer,
            503: OpenApiResponse(description="Veritabanına ulaşılamıyor"),
        }
    )
    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:
            logger.exception("Sağlık kontrolü: veritabanına ulaşılamadı")
            return Response(
                {"status": "error", "database": "unavailable"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        return Response({"status": "ok", "database": "ok"})


def handler404(request, exception):
    if request.path.startswith("/api/"):
        return JsonResponse(error_body("not_found", "Kayıt bulunamadı."), status=404)
    return page_not_found(request, exception)


def handler500(request):
    if request.path.startswith("/api/"):
        return JsonResponse(error_body("server_error", "Beklenmeyen bir hata oluştu."), status=500)
    return server_error(request)
