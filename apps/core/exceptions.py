"""Tek tip hata biçimi: {"error": {"code", "message", "details"}}."""

from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


class APIError(exceptions.APIException):
    """İş kuralı hatası; kod, mesaj ve HTTP durumu çağıran tarafından verilir."""

    def __init__(self, code, message, status_code=status.HTTP_400_BAD_REQUEST, details=None):
        super().__init__(detail=message, code=code)
        self.status_code = status_code
        self.error_code = code
        self.message = message
        self.details = details or {}


def error_body(code, message, details=None):
    return {"error": {"code": code, "message": message, "details": details or {}}}


# DRF istisna sınıfı -> (hata kodu, Türkçe mesaj)
_KNOWN = [
    (exceptions.ValidationError, "validation_error", "Eksik veya geçersiz alan."),
    (exceptions.ParseError, "validation_error", "İstek gövdesi okunamadı."),
    (exceptions.NotAuthenticated, "invalid_token", "Oturum anahtarı eksik veya yanlış."),
    (exceptions.AuthenticationFailed, "invalid_token", "Oturum anahtarı eksik veya yanlış."),
    (exceptions.PermissionDenied, "forbidden", "Bu işlem için yetkin yok."),
    (exceptions.NotFound, "not_found", "Kayıt bulunamadı."),
    (exceptions.MethodNotAllowed, "method_not_allowed", "Bu istek yöntemi desteklenmiyor."),
    (exceptions.UnsupportedMediaType, "validation_error", "İçerik türü desteklenmiyor."),
    (exceptions.Throttled, "rate_limited", "Çok fazla istek gönderdin, biraz bekle."),
]


def api_exception_handler(exc, context):
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()

    if isinstance(exc, APIError):
        response = exception_handler(exc, context)
        response.data = error_body(exc.error_code, exc.message, exc.details)
        return response

    response = exception_handler(exc, context)
    if response is None:
        return None  # beklenmeyen hata: Django 500 üretir

    for exc_class, code, message in _KNOWN:
        if isinstance(exc, exc_class):
            details = exc.detail if isinstance(exc, exceptions.ValidationError) else {}
            if isinstance(details, list):
                details = {"non_field_errors": details}
            if isinstance(exc, exceptions.Throttled) and exc.wait is not None:
                details = {"retry_after_seconds": int(exc.wait)}
            return Response(
                error_body(code, message, details),
                status=response.status_code,
                headers=dict(response.items()),
            )

    return Response(
        error_body("error", str(exc.detail)),
        status=response.status_code,
        headers=dict(response.items()),
    )
