import hashlib
import hmac

from django.conf import settings
from rest_framework.throttling import BaseThrottle


def client_ip(request):
    """İstemci IP'si; vekil sayısı için DRF'nin NUM_PROXIES ayarına uyar."""
    return BaseThrottle().get_ident(request) or ""


def hash_ip(ip):
    """Ham IP saklanmaz; SECRET_KEY ile anahtarlanmış özet tutulur."""
    return hmac.new(settings.SECRET_KEY.encode(), ip.encode(), hashlib.sha256).hexdigest()
