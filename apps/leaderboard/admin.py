from django.contrib import admin

from .models import ScoreEntry


@admin.register(ScoreEntry)
class ScoreEntryAdmin(admin.ModelAdmin):
    """Uygunsuz isimleri silebilmek için; skorlar elle eklenemez ya da değiştirilemez."""

    list_display = ("player_name", "category", "score", "correct_count", "created_at")
    list_filter = ("category",)
    search_fields = ("player_name",)
    ordering = ("-created_at",)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
