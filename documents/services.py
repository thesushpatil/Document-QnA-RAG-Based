import re
import uuid
from functools import lru_cache
from pathlib import Path

import chromadb
from django.conf import settings
from google import genai
from google.genai import types
from pypdf import PdfReader


class RAGError(Exception):
    """Error that can be shown safely to the user in the web page."""

    pass


@lru_cache(maxsize=1)
def get_gemini_client():
    """Create one reusable Gemini client for this running Django process."""
    api_key = settings.GEMINI_API_KEY
    if not api_key:
        raise RAGError("GEMINI_API_KEY is missing from .env.")
    return genai.Client(api_key=api_key)


def get_chroma_collection():
    """Open the local ChromaDB collection used for document chunks."""
    chroma_client = chromadb.PersistentClient(path=str(settings.CHROMA_PATH))
    return chroma_client.get_or_create_collection(
        name=settings.CHROMA_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


def split_text_into_chunks(text, chunk_size=1800, overlap=250):
    """Clean text and split it into overlapping pieces for semantic search."""
    cleaned_text = re.sub(r"\s+", " ", text).strip()
    if not cleaned_text:
        return []
    chunks = []
    start = 0
    while start < len(cleaned_text):
        end = min(start + chunk_size, len(cleaned_text))
        chunk = cleaned_text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == len(cleaned_text):
            break
        start = end - overlap
    return chunks


def create_embeddings(texts, task_type):
    """Turn a list of text strings into Gemini embedding vectors."""
    response = get_gemini_client().models.embed_content(
        model=settings.GEMINI_EMBEDDING_MODEL,
        contents=texts,
        config=types.EmbedContentConfig(task_type=task_type, output_dimensionality=768),
    )
    return [embedding.values for embedding in response.embeddings]


def create_and_index_document(uploaded_file):
    """Save an uploaded PDF, index it, and record its status.

    Shared by the HTML view and the API so the upload flow lives in one place.
    Returns the created Document. On indexing failure the Document is still
    returned with ``indexed=False`` and ``error_message`` populated, and a
    RAGError is raised so callers can report the problem.
    """
    if not uploaded_file.name.lower().endswith(".pdf"):
        raise RAGError("Only PDF files are supported.")

    from .models import Document

    document = Document.objects.create(name=uploaded_file.name, file=uploaded_file)
    try:
        reader, chunk_count = index_document(document)
    except Exception as error:
        document.error_message = str(error)
        document.save(update_fields=["error_message"])
        raise RAGError(str(error)) from error

    document.page_count = len(reader.pages)
    document.chunk_count = chunk_count
    document.indexed = True
    document.save(update_fields=["page_count", "chunk_count", "indexed"])
    return document


def index_document(document):
    """Extract, chunk, embed, and store one uploaded PDF."""
    if Path(document.file.path).suffix.lower() != ".pdf":
        raise RAGError("Only PDF files are supported.")

    reader = PdfReader(document.file.path)
    chunk_records = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        page_chunks = split_text_into_chunks(page_text)
        for chunk_number, chunk_text in enumerate(page_chunks):
            chunk_records.append({
                "text": chunk_text,
                "page": page_number,
                "chunk": chunk_number,
            })

    if not chunk_records:
        raise RAGError("No readable text was found in this PDF.")

    chunk_texts = [record["text"] for record in chunk_records]
    embeddings = create_embeddings(chunk_texts, "RETRIEVAL_DOCUMENT")
    collection = get_chroma_collection()
    ids = [f"{document.pk}-{uuid.uuid4().hex}" for _ in chunk_records]
    collection.add(
        ids=ids,
        documents=chunk_texts,
        embeddings=embeddings,
        metadatas=[
            {
                "document_id": str(document.pk),
                "document_name": document.name,
                "page": record["page"],
                "chunk": record["chunk"],
            }
            for record in chunk_records
        ],
    )
    return reader, len(chunk_records)


def delete_document_data(document):
    """Remove one document from ChromaDB, storage, and the Django database."""
    collection = get_chroma_collection()
    collection.delete(where={"document_id": str(document.pk)})

    if document.file:
        document.file.delete(save=False)

    document.delete()


def answer_question(question, document_ids=None):
    """Retrieve relevant chunks and ask Gemini to answer from those chunks."""
    question = question.strip()
    if not question:
        raise RAGError("Please enter a question.")

    query_embedding = create_embeddings([question], "RETRIEVAL_QUERY")[0]
    collection = get_chroma_collection()
    where = None
    if document_ids:
        where = {"document_id": {"$in": [str(value) for value in document_ids]}}
    result = collection.query(
        query_embeddings=[query_embedding],
        n_results=5,
        where=where,
        include=["documents", "metadatas", "distances"],
    )
    matching_documents = result.get("documents", [[]])[0]
    matching_metadata = result.get("metadatas", [[]])[0]
    if not matching_documents:
        raise RAGError("No indexed document content is available yet. Upload a PDF first.")

    retrieved_context = "\n\n".join(
        f"[Source: {metadata.get('document_name')}, page {metadata.get('page')}]\n{text}"
        for text, metadata in zip(matching_documents, matching_metadata)
    )
    prompt = f"""You answer questions about the user's uploaded personal documents.
Use only the context below. Do not invent facts. If the answer is not in the context, say that you could not find it in the uploaded documents.
Answer clearly and briefly, and mention the relevant source page when useful.

Context:
{retrieved_context}

Question:
{question}
"""
    response = get_gemini_client().models.generate_content(
        model=settings.GEMINI_CHAT_MODEL,
        contents=prompt,
    )
    sources = [
        {"name": metadata.get("document_name"), "page": metadata.get("page")}
        for metadata in matching_metadata
    ]
    return response.text, sources
