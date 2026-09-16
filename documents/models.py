from django.db import models


class Document(models.Model):
    """Store information about an uploaded PDF and its indexing status."""

    name = models.CharField(max_length=255)
    file = models.FileField(upload_to="documents/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    page_count = models.PositiveIntegerField(default=0)
    chunk_count = models.PositiveIntegerField(default=0)
    collection_name = models.CharField(max_length=100, default="personal_documents")
    indexed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]

    def __str__(self):
        return self.name
