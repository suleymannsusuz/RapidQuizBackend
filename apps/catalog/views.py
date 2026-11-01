from rest_framework.generics import ListAPIView

from .models import Category
from .serializers import CategorySerializer


class CategoryListView(ListAPIView):
    """Aktif kategorileri ana sayfadaki sırayla listeler."""

    serializer_class = CategorySerializer
    pagination_class = None
    queryset = Category.objects.filter(is_active=True)
