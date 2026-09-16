from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("name", "indexed", "page_count", "chunk_count", "uploaded_at")
    list_filter = ("indexed", "uploaded_at")
    search_fields = ("name",)
