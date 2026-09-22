# KnowFlow Frontend

Vue 3 frontend for KnowFlow（知汇）.

## Run

Start the backend first:

```powershell
cd D:\bruce\KnowFlow\backend
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend:

```powershell
cd D:\bruce\KnowFlow\frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open the formal entry:

```text
http://127.0.0.1:5173/
```

## Entries

The formal entry `index.html` now mounts the Liquid Glass workbench. `demo.html` renders the same `DemoApp.vue` component as a second entry, so both share one implementation:

- `/` — formal UI (Liquid Glass workbench), served by `index.html` → `src/main.js`
- `/demo.html` — second entry for the same workbench, served by `demo.html` → `src/demo/main.js`

## MVP Features

- Create and select knowledge bases
- Upload `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`
- View parsed document chunks
- Ask RAG questions through `/api/chat`
- View answers, token usage, and retrieved sources
- Save notes and practice, review them under learning records
- Configure providers and clear data under settings
