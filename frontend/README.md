# KnowFlow Frontend

Vue 3 frontend for KnowFlow（知汇）.

## Run

Start the backend first:

```powershell
cd D:\KnowFlow\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend dev server:

```powershell
cd D:\KnowFlow\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open:

```text
http://127.0.0.1:5173/
```

## API base and proxying

`src/api/client.js` sends every request to the same origin by default:

- Dev/preview: Vite proxies `/api` to `http://127.0.0.1:8000` (see `server.proxy`
  and `preview.proxy` in `vite.config.js`), so no CORS setup is needed.
- Production: build the SPA (`npm run build`) and start the backend — it serves
  `frontend/dist` on the same origin when the directory exists.
- Direct backend connection (e.g. separately deployed frontend): set
  `VITE_API_BASE=http://your-backend-origin` before building.

## Features

- Create, rename, and delete knowledge bases; switch between them in the sidebar
- Upload `.txt`, `.md`, `.pdf`, `.docx`, `.pptx` with client-side size/type
  pre-validation (50 MB limit, aligned with the backend `UPLOAD_MAX_BYTES`)
- Track document parsing status, retry failed documents, rebuild the index
- Preview parsed document chunks in the document inspector
- Ask RAG questions through `/api/chat`; see token usage and retrieved sources
  for every answer
- Save notes and exercises, review them under learning records, and mark them
  as reviewed
- Configure providers, retrieval, and privacy modes; export or clear all data
  under settings
