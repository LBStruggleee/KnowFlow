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

Open:

```text
http://127.0.0.1:5173/
```

## MVP Features

- Create and select knowledge bases
- Upload `.txt`, `.md`, `.pdf`, `.docx`, `.pptx`
- View parsed document chunks
- Ask RAG questions through `/api/chat`
- View answers, token usage, and retrieved sources
