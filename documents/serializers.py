from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    """Read-only representation of a stored document and its indexing status."""

    class Meta:
        model = Document
        fields = [
            "id",
            "name",
            "file",
            "uploaded_at",
            "page_count",
            "chunk_count",
            "collection_name",
            "indexed",
            "error_message",
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    """Validate a PDF upload before it is indexed."""

    file = serializers.FileField()

    def validate_file(self, uploaded_file):
        if not uploaded_file.name.lower().endswith(".pdf"):
            raise serializers.ValidationError("Only PDF files are supported.")
        return uploaded_file


class AskSerializer(serializers.Serializer):
    """Validate a question and optional document filter for the RAG query."""

    question = serializers.CharField()
    document_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
    )


class SourceSerializer(serializers.Serializer):
    """A single retrieved source shown alongside an answer."""

    name = serializers.CharField()
    page = serializers.IntegerField()


class AnswerSerializer(serializers.Serializer):
    """The answer payload returned by the ask endpoint."""

    question = serializers.CharField()
    answer = serializers.CharField()
    sources = SourceSerializer(many=True)
