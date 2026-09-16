# Personal Document Q&A System (RAG with Django + Gemini + ChromaDB)

A web application that lets you upload personal PDFs (resumes, ebooks, notes) and ask
natural-language questions about them. Answers are **grounded** in your uploaded
documents using a **Retrieval-Augmented Generation (RAG)** pipeline, so the model
answers from *your* content instead of guessing.

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
7. [The RAG Pipeline (Component by Component, with Examples)](#7-the-rag-pipeline-component-by-component-with-examples)
8. [How the LLM Is Used](#8-how-the-llm-is-used)
9. [Data Model](#9-data-model)
10. [Configuration (.env)](#10-configuration-env)
11. [Run Locally](#11-run-locally)
12. [Common Interview Questions & Answers](#12-common-interview-questions--answers)
13. [Limitations & Future Work](#13-limitations--future-work)

---

## 1. What This Project Does

- Upload a **PDF** through a web page.
- The system **extracts text**, **splits it into chunks**, **embeds** each chunk into a
  vector, and **stores** those vectors in a local vector database (ChromaDB).
- You then **ask a question**. The question is embedded, the most relevant chunks are
  **retrieved** by semantic similarity, and a **Large Language Model (Gemini)** writes an
  answer using *only* those retrieved chunks.
- The answer is shown along with the **source document name and page numbers**.

This is a classic **RAG (Retrieval-Augmented Generation)** system: retrieval brings in
facts, generation turns them into a readable answer.

---

## 2. Tech Stack

| Layer | Technology | Role |
|-------|-----------|------|
| Web framework | **Django 5.2+** | Routing, views, templates, admin, ORM |
| Database (metadata) | **SQLite** (`db.sqlite3`) | Stores `Document` records + indexing status |
| Vector database | **ChromaDB** (`chroma_db/`) | Stores chunk text, embeddings, metadata |
| PDF parsing | **pypdf** | Extract text from PDF pages |
| Embeddings | **Google Gemini** (`gemini-embedding-001`) | Turn text into 768-dim vectors |
| LLM / generation | **Google Gemini** (`gemini` chat model) | Generate grounded answers |
| Config | **python-dotenv** | Load secrets/settings from `.env` |
| Frontend | **Django templates + vanilla HTML/CSS** | Upload + chat UI |

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
├── templates/documents/home.html  # Active UI (upload + chat)
│
├── rag_project/                   # Django project config
│   ├── settings.py                # Django, Gemini, media, ChromaDB config
│   ├── urls.py                    # Root URL routing + media serving in DEBUG
│   └── wsgi.py                    # WSGI entry point
│
└── documents/                     # Main Django app
    ├── models.py                  # Document model (metadata + status)
    ├── views.py                   # Upload / delete / ask request handlers
    ├── services.py                # ★ RAG core: extract, chunk, embed, retrieve, answer
    ├── urls.py                    # App URL routing
    ├── admin.py                   # Django admin registration
    ├── apps.py                    # App config
    └── migrations/                # DB schema migrations
```

The **heart of the project is `documents/services.py`** — it contains the entire RAG
pipeline.

---

## 4. Feature List (Every Functionality)

### Document Management
- **Upload PDF** — Upload a PDF via the web form. Only `.pdf` files are accepted
  (validated by extension). Non-PDF uploads are rejected with an error message.
- **Automatic indexing on upload** — As soon as a PDF is uploaded, it is parsed,
  chunked, embedded, and stored in the vector database in one step.
- **Indexing status tracking** — Each document records `page_count`, `chunk_count`,
  `indexed` (boolean), and an `error_message` if indexing failed.
- **Document library view** — The sidebar lists all uploaded documents with page count,
  chunk count, and an "Indexed" badge.
- **Delete document** — Deletes the document from **three places** at once: the vector
  DB (all its chunks), the media file on disk, and the SQLite record. Confirmation
  prompt in the UI prevents accidental deletion.
- **Error surfacing** — Any failure (missing API key, unreadable PDF, no extractable
  text) is shown to the user as a friendly message via Django's messages framework.

### Question Answering
- **Ask a question** — Type a natural-language question in the chat box.
- **Semantic retrieval** — Retrieves the 5 most relevant chunks across all documents by
  vector similarity (cosine distance).
- **Optional document filtering** — `answer_question()` supports a `document_ids`
  filter so retrieval can be scoped to specific documents (the plumbing exists; UI
  currently asks across all documents).
- **Grounded answer generation** — Gemini answers using only the retrieved context and
  is instructed to say it "could not find it" when the answer isn't present (reduces
  hallucination).
- **Source citations** — Each answer displays the source document name and page numbers
  the answer was drawn from.

### Platform / Framework Features
- **Django admin** — `Document` records are manageable at `/admin/` with list display,
  filters, and search by name.
- **Environment-driven config** — Models, hosts, API keys, and paths are all read from
  `.env` so no secrets are hardcoded.
- **Persistent vector store** — ChromaDB is a `PersistentClient`, so embeddings survive
  server restarts.
- **Reusable Gemini client** — The Gemini client is cached (`lru_cache`) so one client
  is reused per running process.
- **Media serving in DEBUG** — Uploaded PDFs are served directly during development.

---

## 5. High-Level Architecture

```
                        ┌───────────────────────────────────────────────┐
                        │                   Browser (UI)                  │
                        │        templates/documents/home.html            │
                        │   Upload form · Ask form · Document library     │
                        └───────────────┬─────────────────┬───────────────┘
                                        │ POST            │ POST
                             (action=upload/delete)  (action=ask)
                                        ▼                 ▼
                        ┌───────────────────────────────────────────────┐
                        │              Django View (views.py)             │
                        │   home() dispatches to handlers by "action"     │
                        └───────────────┬─────────────────┬───────────────┘
                                        │                 │
                          index_document()/         answer_question()
                          delete_document_data()          │
                                        ▼                 ▼
                        ┌───────────────────────────────────────────────┐
                        │            RAG Core (services.py)               │
                        │  pypdf · chunking · embeddings · retrieval ·    │
                        │  prompt building · generation                   │
                        └───┬──────────────┬──────────────┬───────────────┘
                            │              │              │
                            ▼              ▼              ▼
                   ┌──────────────┐ ┌────────────┐ ┌──────────────┐
                   │  SQLite      │ │  ChromaDB  │ │  Gemini API  │
                   │ (metadata)   │ │ (vectors)  │ │ (embed+chat) │
                   └──────────────┘ └────────────┘ └──────────────┘
```

**Two data stores, by design:**
- **SQLite** holds *document metadata* (name, page/chunk counts, status). Good for
  relational queries and the admin UI.
- **ChromaDB** holds *chunk text + embedding vectors + metadata*. Good for fast semantic
  (vector) similarity search.

---

## 6. End-to-End Workflow

### A. Indexing (happens once per uploaded PDF)
1. User uploads a PDF → `views.handle_document_upload()`.
2. A `Document` row is created in SQLite.
3. `services.index_document()` runs:
   - `pypdf` extracts text page by page.
   - Each page's text is split into overlapping chunks.
   - Gemini embeds all chunks (`task_type="RETRIEVAL_DOCUMENT"`).
   - Chunks + embeddings + metadata are stored in ChromaDB.
4. The `Document` row is updated with `page_count`, `chunk_count`, `indexed=True`.

### B. Querying (happens every time a question is asked)
1. User submits a question → `views.home()` with `action="ask"`.
2. `services.answer_question()` runs:
   - Embed the question (`task_type="RETRIEVAL_QUERY"`).
   - Query ChromaDB for the top 5 most similar chunks.
   - Build a prompt containing the retrieved context + the question.
   - Send the prompt to Gemini's chat model.
3. The answer + source (name, page) list are rendered back into the page.

---

## 7. The RAG Pipeline (Component by Component, with Examples)

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

## 8. How the LLM Is Used

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

## 9. Data Model

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

## 10. Configuration (.env)

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

## 11. Run Locally

Use the workspace virtual environment (PowerShell on Windows):

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Then open `http://127.0.0.1:8000/`.

Useful commands:

```powershell
python manage.py makemigrations
python manage.py migrate
python manage.py check
python manage.py createsuperuser   # to use /admin
```

---

## 12. Common Interview Questions & Answers

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

---

## 13. Limitations & Future Work

- **Text-only PDFs:** scanned/image PDFs aren't supported (would need OCR, e.g.
  Tesseract).
- **No chat history / multi-turn memory:** each question is answered independently.
- **Fixed top-k = 5:** retrieval depth isn't tunable from the UI.
- **No per-document scoping in UI:** the backend supports `document_ids` filtering, but
  the UI asks across all documents.
- **No authentication:** anyone with access can upload/query; add login for multi-user.
- **Synchronous indexing:** large PDFs block the request; a background task queue (e.g.
  Celery) would improve UX.
- **Basic error handling:** could add retries/rate-limit handling for the Gemini API.
