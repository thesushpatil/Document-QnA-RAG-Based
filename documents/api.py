from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document
from .serializers import (
    AnswerSerializer,
    AskSerializer,
    DocumentSerializer,
    DocumentUploadSerializer,
)
from .services import (
    RAGError,
    answer_question,
    create_and_index_document,
    delete_document_data,
)


class DocumentListCreateAPIView(ListAPIView):
    """GET lists all documents. POST uploads and indexes a new PDF."""

    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        upload_serializer = DocumentUploadSerializer(data=request.data)
        upload_serializer.is_valid(raise_exception=True)
        uploaded_file = upload_serializer.validated_data["file"]

        try:
            document = create_and_index_document(uploaded_file)
        except RAGError as error:
            return Response(
                {"detail": f"Indexing failed: {error}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            DocumentSerializer(document).data,
            status=status.HTTP_201_CREATED,
        )


class DocumentDetailAPIView(APIView):
    """GET retrieves one document. DELETE removes it from all stores."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get_object(self, pk):
        return Document.objects.filter(pk=pk).first()

    def get(self, request, pk):
        document = self.get_object(pk)
        if not document:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(DocumentSerializer(document).data)

    def delete(self, request, pk):
        document = self.get_object(pk)
        if not document:
            return Response(
                {"detail": "Document not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        try:
            delete_document_data(document)
        except Exception as error:  # noqa: BLE001 - surface delete failures safely
            return Response(
                {"detail": f"Could not delete document: {error}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class AskAPIView(APIView):
    """POST a question and receive a grounded answer with sources."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        ask_serializer = AskSerializer(data=request.data)
        ask_serializer.is_valid(raise_exception=True)
        question = ask_serializer.validated_data["question"]
        document_ids = ask_serializer.validated_data.get("document_ids") or None

        try:
            answer_text, sources = answer_question(question, document_ids=document_ids)
        except RAGError as error:
            return Response(
                {"detail": str(error)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception as error:  # noqa: BLE001 - surface generation errors safely
            return Response(
                {"detail": f"Answer generation failed: {error}"},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        payload = {"question": question, "answer": answer_text, "sources": sources}
        return Response(AnswerSerializer(payload).data)
