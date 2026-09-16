# Document Q&A System (RAG with Django REST Framework + Gemini + ChromaDB)

A decoupled web application that lets you upload PDFs (resumes, ebooks, notes) and ask
natural-language questions about them. Answers are **grounded** in your uploaded
documents using a **Retrieval-Augmented Generation (RAG)** pipeline, so the model
answers from *your* content instead of guessing.

The backend is a **Django REST Framework (DRF) API** that can be tested independently
(Postman, curl, or the DRF browsable API). The frontend is a thin JavaScript
single-page client that calls the same API — so the frontend and backend are fully
separated.

> Interview-ready README: it documents every feature, explains the full RAG pipeline
> with examples and sample outputs per component, describes how the LLM is used, and
> lays out the architecture and end-to-end workflow.

---

## Table of Contents

1. [What This Project Does](#1-what-this-project-does)
2. [Tech Stack](#2-tech-stack)
3. [Project Structure](#3-project-structure)
4. [Feature List (Every Functionality)](#4-feature-list-every-functionality)
5. [High-Level Architecture](#5-high-level-architecture)
6. [End-to-End Workflow](#6-end-to-end-workflow)
7. [API Endpoints](#7-api-endpoints)
8. [The RAG Pipeline (Component by Component, with Examples)](#8-the-rag-pipeline-component-by-component-with-examples)
9. [How the LLM Is Used](#9-how-the-llm-is-used)
10. [Data Model](#10-data-model)
11. [Configuration (.env)](#11-configuration-env)
12. [Run Locally](#12-run-locally)
13. [Common Interview Questions & Answers](#13-common-interview-questions--answers)
14. [Limitations & Future Work](#14-limitations--future-work)

---

## 1. What This Project Does

- Upload a **PDF** (via the REST API or the web page).
- The system **extracts text**, **splits it into chunks**, **embeds** each chunk into a
  vector, and **stores** those vectors in a local vector database (ChromaDB).
- You then **ask a question**. The question is embedded, the most relevant chunks are
  **retrieved** by semantic similarity, and a **Large Language Model (Gemini)** writes an
  answer using *only* those retrieved chunks.
- The answer is returned as JSON with the **source document name and page numbers**.

This is a classic **RAG (Retrieval-Augmented Generation)** system: retrieval brings in
facts, generation turns them into a readable answer.

**Architecture note:** all operations are exposed as a **DRF REST API**. The HTML page
is a thin JavaScript client that consumes that API — the same endpoints you can hit in
Postman. Business logic lives in a reusable **service layer** (`services.py`), separate
from both the API and the frontend.

---

## 2. Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Web framework | **Django 5.2+** | Project, ORM, admin, URL routing |
| REST API | **Django REST Framework** | JSON API: serializers, views, validation |
| Database (metadata) | **SQLite** (`db.sqlite3`) | Stores `Document` records + indexing status |
| Vector database | **ChromaDB** (`chroma_db/`) | Stores chunk text, embeddings, metadata |
| PDF parsing | **pypdf** | Extract text from PDF pages |
| Embeddings | **Google Gemini** (`gemini-embedding-001`) | Turn text into 768-dim vectors |
| LLM / generation | **Google Gemini** (`gemini` chat model) | Generate grounded answers |
| Config | **python-dotenv** | Load secrets/settings from `.env` |
| Frontend | **Vanilla HTML/CSS + JavaScript (`fetch`)** | Thin client that calls the REST API |

---

## 3. Project Structure

```
Document Q&A System/
├── manage.py                      # Django entry point
├── requirements.txt               # Python dependencies
├── .env                           # Secrets & config (NOT committed)
├── db.sqlite3                     # Document metadata (SQLite)
├── chroma_db/                     # Persistent local vector store (ChromaDB)
├── media/documents/               # Uploaded PDF files
├── templates/documents/home.html  # Thin JS frontend (calls the REST API)
│
├── rag_project/                   # Django project config
│   ├── settings.py                # Django, DRF, Gemini, media, ChromaDB config
│   ├── urls.py                    # Root URL routing + media serving in DEBUG
│   └── wsgi.py                    # WSGI entry point
│
└── documents/                     # Main Django app
    ├── models.py                  # Document model (metadata + status)
    ├── serializers.py             # DRF serializers (validation + JSON shaping)
    ├── api.py                     # ★ DRF API views (upload, list, delete, ask)
    ├── views.py                   # Single view: serves the HTML shell (no logic)
    ├── services.py                # ★ RAG core: extract, chunk, embed, retrieve, answer
    ├── urls.py                    # App URL routing (HTML page + API routes)
    ├── admin.py                   # Django admin registration
    ├── apps.py                    # App config
    └── migrations/                # DB schema migrations
```

Two files carry the weight:
- **`documents/services.py`** — the entire RAG pipeline + shared orchestration.
- **`documents/api.py`** — the REST API layer (thin; delegates to `services.py`).

`views.py` is deliberately tiny — it only renders the HTML page. All real work happens
through the API, so the backend is fully testable on its own.

---

## 4. Feature List (Every Functionality)

### Document Management
- **Upload PDF (API)** — `POST /api/documents/` with a multipart `file`. Only `.pdf`
  files are accepted (validated by a DRF serializer). Non-PDF uploads return `400`.
- **Automatic indexing on upload** — As soon as a PDF is uploaded, it is parsed,
  chunked, embedded, and stored in the vector database in one step
  (`services.create_and_index_document()`).
- **Indexing status tracking** — Each document records `page_count`, `chunk_count`,
  `indexed` (boolean), and an `error_message` if indexing failed.
- **List documents (API)** — `GET /api/documents/` returns all documents as JSON with
  page count, chunk count, and indexing status. The frontend renders this list.
- **Delete document (API)** — `DELETE /api/documents/<id>/` removes the document from
  **three places** at once: the vector DB (all its chunks), the media file on disk, and
  the SQLite record. The frontend adds a confirmation prompt.
- **Structured error handling** — Failures return JSON `{"detail": "..."}` with the
  right HTTP status (`400` for validation/RAG errors, `404` not found, `502` for
  Gemini failures).

### Question Answering
- **Ask a question (API)** — `POST /api/ask/` with JSON `{"question": "..."}`.
- **Semantic retrieval** — Retrieves the 5 most relevant chunks across all documents by
  vector similarity (cosine distance).
- **Optional document filtering** — `POST /api/ask/` accepts an optional `document_ids`
  list to scope retrieval to specific documents.
- **Grounded answer generation** — Gemini answers using only the retrieved context and
  is instructed to say it "could not find it" when the answer isn't present (reduces
  hallucination).
- **Source citations** — The response includes a `sources` array of `{name, page}` the
  answer was drawn from.

### Platform / Framework Features
- **Decoupled frontend/backend** — The DRF API is the single backend; the HTML page is a
  thin JS client using `fetch`. The API is CSRF-exempt and open (`AllowAny`) for easy
  Postman/browser testing.
- **DRF browsable API** — Every endpoint has an interactive UI in the browser.
- **Reusable service layer** — Upload/index/retrieve/answer logic lives in
  `services.py`, called by the API (and re-usable anywhere) — not duplicated in views.
- **Django admin** — `Document` records are manageable at `/admin/` with list display,
  filters, and search by name.
- **Environment-driven config** — Hosts, API keys, model names, and paths are all read
  from `.env` so no secrets are hardcoded.
- **Persistent vector store** — ChromaDB is a `PersistentClient`, so embeddings survive
  server restarts.
- **Reusable Gemini client** — The Gemini client is cached (`lru_cache`) so one client
  is reused per running process.
- **Media serving in DEBUG** — Uploaded PDFs are served directly during development.

---

## 5. High-Level Architecture

```
        ┌─────────────────────────┐          ┌─────────────────────────┐
        │   JS Frontend (fetch)   │          │   Postman / curl / DRF  │
        │  templates/home.html    │          │      browsable API      │
        └────────────┬────────────┘          └────────────┬────────────┘
                     │ HTTP + JSON                         │ HTTP + JSON
                     └──────────────────┬──────────────────┘
                                        ▼
                        ┌───────────────────────────────────────────────┐
                        │            DRF REST API (api.py)                │
                        │  GET/POST /api/documents/                       │
                        │  GET/DELETE /api/documents/<id>/                │
                        │  POST /api/ask/                                 │
                        │  (serializers.py handles validation + JSON)     │
                        └───────────────────────┬─────────────────────────┘
                                                │ calls
                                                ▼
                        ┌───────────────────────────────────────────────┐
                        │          Service Layer (services.py)            │
                        │  create_and_index_document · answer_question ·  │
                        │  pypdf · chunking · embeddings · retrieval ·    │
                        │  prompt building · generation · delete          │
                        └───┬──────────────┬──────────────┬───────────────┘
                            │              │              │
                            ▼              ▼              ▼
                   ┌──────────────┐ ┌────────────┐ ┌──────────────┐
                   │  SQLite      │ │  ChromaDB  │ │  Gemini API  │
                   │ (metadata)   │ │ (vectors)  │ │ (embed+chat) │
                   └──────────────┘ └────────────┘ └──────────────┘

        views.py → serves only the HTML shell (no business logic).
```

**Layered by responsibility:**
- **Frontend / API clients** — anything that speaks HTTP+JSON (the JS page, Postman).
- **API layer (`api.py` + `serializers.py`)** — validates input, shapes JSON, maps
  errors to HTTP status codes. Thin; no RAG logic.
- **Service layer (`services.py`)** — all business/RAG logic. Reusable, framework-light.
- **Data layer** — SQLite (metadata), ChromaDB (vectors), Gemini (embed + generate).

**Two data stores, by design:**
- **SQLite** holds *document metadata* (name, page/chunk counts, status). Good for
  relational queries and the admin UI.
- **ChromaDB** holds *chunk text + embedding vectors + metadata*. Good for fast semantic
  (vector) similarity search.

---

## 6. End-to-End Workflow

### A. Indexing (happens once per uploaded PDF)
1. Client calls `POST /api/documents/` with a PDF → `api.DocumentListCreateAPIView`.
2. `DocumentUploadSerializer` validates the file is a `.pdf`.
3. `services.create_and_index_document()` runs:
   - Creates a `Document` row in SQLite.
   - `pypdf` extracts text page by page.
   - Each page's text is split into overlapping chunks.
   - Gemini embeds all chunks (`task_type="RETRIEVAL_DOCUMENT"`).
   - Chunks + embeddings + metadata are stored in ChromaDB.
   - The `Document` row is updated with `page_count`, `chunk_count`, `indexed=True`.
4. The API returns the created document as JSON (`201`).

### B. Querying (happens every time a question is asked)
1. Client calls `POST /api/ask/` with `{"question": "..."}` → `api.AskAPIView`.
2. `AskSerializer` validates the question (and optional `document_ids`).
3. `services.answer_question()` runs:
   - Embed the question (`task_type="RETRIEVAL_QUERY"`).
   - Query ChromaDB for the top 5 most similar chunks.
   - Build a prompt containing the retrieved context + the question.
   - Send the prompt to Gemini's chat model.
4. The API returns JSON: `{"question": ..., "answer": ..., "sources": [{name, page}]}`.

---

## 7. API Endpoints

All endpoints are CSRF-exempt and open (`AllowAny`) for easy testing. Base URL in
development: `http://127.0.0.1:8000`.

| Method | Endpoint | Body | Success | Purpose |
|--------|----------|------|---------|---------|
| `GET` | `/api/documents/` | — | `200` | List all documents (JSON) |
| `POST` | `/api/documents/` | multipart `file` | `201` | Upload + index a PDF |
| `GET` | `/api/documents/<id>/` | — | `200` | Retrieve one document |
| `DELETE` | `/api/documents/<id>/` | — | `204` | Delete from all stores |
| `POST` | `/api/ask/` | JSON `{"question": "...", "document_ids": [1,2]?}` | `200` | Ask a grounded question |
| `GET` | `/` | — | `200` | HTML frontend (JS client) |

**Example — ask a question (curl):**
```bash
curl -X POST http://127.0.0.1:8000/api/ask/ \
  -H "Content-Type: application/json" \
  -d '{"question": "What backend experience do I have?"}'
```

**Example response:**
```json
{
  "question": "What backend experience do I have?",
  "answer": "Based on your documents, you worked as a Backend Developer Intern ...",
  "sources": [
    {"name": "Sushant_Patil-CSE.pdf", "page": 2},
    {"name": "Sushant_Patil-CSE.pdf", "page": 1}
  ]
}
```

**Error shape (all endpoints):** `{"detail": "message"}` with an appropriate status
(`400` validation/RAG error, `404` not found, `502` Gemini/generation failure).

---

## 8. The RAG Pipeline (Component by Component, with Examples)

RAG = **R**etrieval **A**ugmented **G**eneration. Instead of asking the LLM to answer
from memory, we *retrieve* relevant facts from the user's documents and *augment* the
LLM prompt with them. Below is each stage with an example input and output.

### Stage 1 — PDF Text Extraction
**Code:** `PdfReader(document.file.path)` in `index_document()`
**What it does:** Reads each PDF page and pulls out raw text.

- **Input (example):** `Sushant_Patil-CSE.pdf` (a 2-page resume PDF)
- **Output (example):**
  ```
  Page 1: "Sushant Patil   Computer Science Engineer   Skills: Python, Django, REST APIs ..."
  Page 2: "Experience: Backend Developer Intern ...  Projects: Document Q&A System ..."
  ```
> Note: `pypdf` only extracts *text*. Scanned/image-only PDFs return empty text and are
> rejected ("No readable text was found in this PDF.").

---

### Stage 2 — Text Chunking (with overlap)
**Code:** `split_text_into_chunks(text, chunk_size=1800, overlap=250)`
**What it does:** Cleans whitespace and cuts text into ~1800-character pieces that
**overlap by 250 characters**, so a sentence split across a boundary isn't lost.

- **Input (example):** a 4000-character page of text
- **Output (example):** 3 chunks
  ```
  chunk 0: chars    0 – 1800
  chunk 1: chars 1550 – 3350   (overlaps chunk 0 by 250)
  chunk 2: chars 3100 – 4000   (overlaps chunk 1 by 250)
  ```

**Why chunk?**
- Embedding models and LLMs have size limits.
- Smaller chunks give **more precise retrieval** (you match the exact relevant passage,
  not a whole page).
- Overlap preserves context across cut points.

---

### Stage 3 — Embedding (text → vector)
**Code:** `create_embeddings(texts, task_type)` → Gemini `embed_content`
**What it does:** Converts each chunk of text into a **768-dimensional vector** that
captures its meaning. Similar meanings → nearby vectors.

- **Input (example):** `"Skills: Python, Django, REST APIs"`
- **Output (example):** a 768-number vector
  ```
  [0.0123, -0.0456, 0.0789, ... , 0.0021]   # length = 768
  ```

**Key detail — task types:**
- Documents are embedded with `task_type="RETRIEVAL_DOCUMENT"`.
- Questions are embedded with `task_type="RETRIEVAL_QUERY"`.
- Using matching task types tells Gemini to optimize the vectors for
  document-vs-query similarity search, which improves retrieval quality.

---

### Stage 4 — Vector Storage (ChromaDB)
**Code:** `collection.add(ids, documents, embeddings, metadatas)`
**What it does:** Stores each chunk's text, its embedding, and metadata in a persistent
ChromaDB collection configured for **cosine similarity** (`hnsw:space: cosine`).

- **Input (example):** one chunk record
  ```json
  {
    "id": "3-9f2ac1...",
    "document": "Skills: Python, Django, REST APIs",
    "embedding": [0.0123, -0.0456, ...],
    "metadata": {
      "document_id": "3",
      "document_name": "Sushant_Patil-CSE.pdf",
      "page": 1,
      "chunk": 0
    }
  }
  ```
- **Output:** stored and searchable. Survives server restarts (persistent client).

**Why a vector DB?** It performs fast **approximate nearest-neighbor** search over
thousands of vectors, so you can find "closest in meaning" chunks in milliseconds.

---

### Stage 5 — Retrieval (semantic search)
**Code:** `collection.query(query_embeddings=[...], n_results=5, ...)`
**What it does:** Embeds the question, then finds the **top 5** most similar chunks by
cosine distance. Optionally filters by `document_id`.

- **Input (example):** question `"What backend experience do I have?"`
  → embedded as a RETRIEVAL_QUERY vector.
- **Output (example):** top 5 chunks, e.g.
  ```
  1. "Experience: Backend Developer Intern ..."   (page 2, distance 0.14)
  2. "Skills: Python, Django, REST APIs ..."       (page 1, distance 0.21)
  3. "Projects: Document Q&A System ..."           (page 2, distance 0.28)
  ...
  ```
Lower distance = more similar. These chunks become the "context".

---

### Stage 6 — Prompt Augmentation
**Code:** the `prompt = f"""..."""` block in `answer_question()`
**What it does:** Combines the retrieved chunks + the question into a single instruction
for the LLM, with guardrails.

- **Output (example prompt sent to Gemini):**
  ```
  You answer questions about the user's uploaded personal documents.
  Use only the context below. Do not invent facts. If the answer is not in
  the context, say that you could not find it in the uploaded documents.
  Answer clearly and briefly, and mention the relevant source page when useful.

  Context:
  [Source: Sushant_Patil-CSE.pdf, page 2]
  Experience: Backend Developer Intern ...

  [Source: Sushant_Patil-CSE.pdf, page 1]
  Skills: Python, Django, REST APIs ...

  Question:
  What backend experience do I have?
  ```

The phrase **"Use only the context below. Do not invent facts."** is what keeps the
model **grounded** and reduces hallucination.

---

### Stage 7 — Generation (the LLM answer)
**Code:** `get_gemini_client().models.generate_content(model=..., contents=prompt)`
**What it does:** Gemini reads the augmented prompt and writes a concise, grounded
answer.

- **Input:** the prompt above
- **Output (example answer):**
  ```
  Based on your documents, you worked as a Backend Developer Intern, using Python
  and Django to build REST APIs, and you built a Document Q&A System project
  (see page 2).
  ```
- **Sources returned to UI:**
  ```
  Sushant_Patil-CSE.pdf · page 2
  Sushant_Patil-CSE.pdf · page 1
  ```

---

## 9. How the LLM Is Used

This project uses **Google Gemini** in **two distinct roles**:

| Role | Model (default) | Function | Called by |
|------|-----------------|----------|-----------|
| **Embedding model** | `gemini-embedding-001` | Convert text → 768-dim vectors for search | `create_embeddings()` |
| **Chat / generation model** | `gemini` chat model (from `GEMINI_CHAT_MODEL`) | Read retrieved context + write the final answer | `answer_question()` |

**Important distinction for interviews:**
- The **embedding model** does *not* generate answers. It only turns text into vectors so
  we can measure semantic similarity. It runs during indexing (documents) and during
  querying (the question).
- The **chat model (generation LLM)** only runs at answer time. It never sees the whole
  document — it only sees the **retrieved chunks**. This is the core RAG idea: the LLM is
  "augmented" with just-in-time retrieved facts.

**Why RAG instead of just asking the LLM?**
- The LLM has no knowledge of your private PDFs.
- RAG injects your document content at query time, so answers are specific, current, and
  **cite sources** — without retraining or fine-tuning the model.
- It reduces hallucination because the model is told to answer only from provided context.

---

## 10. Data Model

`documents/models.py` — the `Document` model (stored in SQLite):

| Field | Type | Purpose |
|-------|------|---------|
| `name` | CharField | Original file name |
| `file` | FileField | Uploaded PDF (stored in `media/documents/`) |
| `uploaded_at` | DateTimeField | Upload timestamp (auto) |
| `page_count` | PositiveIntegerField | Number of PDF pages |
| `chunk_count` | PositiveIntegerField | Number of chunks created |
| `collection_name` | CharField | ChromaDB collection name |
| `indexed` | BooleanField | Whether indexing succeeded |
| `error_message` | TextField | Stored error if indexing failed |

Ordering: newest first (`-uploaded_at`). Registered in the Django admin with list
display, filters, and search.

---

## 11. Configuration (.env)

All configuration is read from `.env` via `python-dotenv`. Key variables:

| Variable | Purpose |
|----------|---------|
| `GEMINI_API_KEY` | **Required.** Google Gemini API key (keep secret) |
| `GEMINI_CHAT_MODEL` | Chat/generation model name |
| `GEMINI_EMBEDDING_MODEL` | Embedding model name |
| `CHROMA_PATH` | Folder for the persistent vector store |
| `CHROMA_COLLECTION` | Vector collection name |
| `DJANGO_SECRET_KEY` | Django secret key |
| `DEBUG` | `1` for development |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts |
| `MEDIA_ROOT` / `MEDIA_URL` | Uploaded file storage/serving |

> **Security:** never commit `.env`. If a key was ever committed, rotate it. Add `.env`
> to `.gitignore`.

---

## 12. Run Locally

Use the workspace virtual environment (PowerShell on Windows):

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

**Use it two ways:**
- **Frontend:** open `http://127.0.0.1:8000/` — the JS page drives the API.
- **API directly:** hit the endpoints in Postman/curl, or use the DRF browsable API by
  visiting `http://127.0.0.1:8000/api/documents/` in a browser.

Useful commands:

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py createsuperuser   # to use /admin
```

---

## 13. Common Interview Questions & Answers

**Q: What is RAG and why use it here?**
Retrieval-Augmented Generation. The LLM doesn't know your private PDFs, so we retrieve
the most relevant chunks and add them to the prompt. This gives accurate, source-cited
answers without fine-tuning the model.

**Q: Why chunk the text? Why overlap?**
Chunking keeps pieces within model limits and makes retrieval precise (match a passage,
not a whole page). Overlap (250 chars) prevents losing context at chunk boundaries.

**Q: Why two databases (SQLite + ChromaDB)?**
SQLite stores relational metadata and powers the admin UI. ChromaDB stores embeddings
and does fast vector similarity search — something relational DBs aren't optimized for.

**Q: What's the difference between the embedding model and the chat model?**
The embedding model turns text into vectors for similarity search; it never writes
answers. The chat model reads the retrieved context and generates the final answer.

**Q: How do you prevent hallucination?**
The prompt instructs the model to use only the provided context and to say it couldn't
find the answer when the context lacks it. Answers also cite source pages.

**Q: What are RETRIEVAL_DOCUMENT vs RETRIEVAL_QUERY task types?**
They tell Gemini to optimize embeddings for the document side vs the query side of a
search, improving match quality between questions and stored chunks.

**Q: How does similarity search work?**
ChromaDB uses cosine distance (`hnsw:space: cosine`) with an HNSW index to find the
nearest vectors to the question embedding. We take the top 5.

**Q: What happens on delete?**
`delete_document_data()` removes the chunks from ChromaDB (by `document_id`), deletes the
file from disk, and deletes the SQLite record — keeping all three stores consistent.

**Q: How is the backend decoupled from the frontend?**
All operations are exposed through a Django REST Framework API (`api.py`). The HTML page
is a thin JavaScript client that calls those endpoints with `fetch`. Because the API
returns JSON and holds no presentation logic, it can be tested standalone in Postman and
the frontend could be swapped for React/Vue without touching the backend.

**Q: Why a separate service layer?**
`services.py` holds all business/RAG logic so it isn't duplicated across the API and any
other caller. The API layer stays thin — it validates input, calls a service function,
and shapes the JSON response. This keeps concerns separated and the logic reusable.

**Q: How do the serializers help?**
DRF serializers validate and shape data at the boundary. `DocumentUploadSerializer`
rejects non-PDFs, `AskSerializer` validates the question and optional `document_ids`, and
`DocumentSerializer`/`AnswerSerializer` produce consistent JSON responses.

---

## 14. Limitations & Future Work

- **Text-only PDFs:** scanned/image PDFs aren't supported (would need OCR, e.g.
  Tesseract).
- **No chat history / multi-turn memory:** each question is answered independently.
- **Fixed top-k = 5:** retrieval depth isn't tunable from the request.
- **No authentication:** the API is open (`AllowAny`) and CSRF-exempt for easy testing;
  add token/session auth before deploying for multi-user use.
- **Synchronous indexing:** large PDFs block the request; a background task queue (e.g.
  Celery) would improve UX.
- **Basic error handling:** could add retries/rate-limit handling for the Gemini API.
