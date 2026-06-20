# KnowFlow Backend

FastAPI backend for KnowFlow（知汇）.

## Run

```powershell
cd D:\bruce\KnowFlow\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

## Environment

Create `.env` from `.env.example`:

```powershell
Copy-Item .env.example .env
```

Then set your DashScope API key:

```env
DASHSCOPE_API_KEY=your_dashscope_api_key
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

## Check

- Health: http://127.0.0.1:8000/api/health
- Swagger: http://127.0.0.1:8000/docs

## Knowledge Base API

Create a knowledge base:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/kbs" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"name":"Spark KB","description":"Spark learning materials","category":"Spark"}'
```

List knowledge bases:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/kbs"
```

Get one knowledge base:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/kbs/1"
```

## Document API

Supported document types:

```text
.txt
.md
.pdf
.docx
.pptx
```

Upload a document:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/kbs/1/documents/upload" `
  -Method Post `
  -Form @{ file = Get-Item "D:\bruce\KnowFlow\backend\sample.md" }
```

List documents in a knowledge base:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/kbs/1/documents"
```

Get one document:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/documents/1"
```

List document chunks:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/documents/1/chunks"
```

Search vectorized chunks:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/kbs/1/search" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"query":"Spark RDD","top_k":3}'
```

## RAG Chat API

Ask a question:

```powershell
Invoke-RestMethod `
  -Uri "http://127.0.0.1:8000/api/chat" `
  -Method Post `
  -ContentType "application/json; charset=utf-8" `
  -Body '{"kb_id":1,"question":"Spark DataFrame 和 RDD 有什么区别？","top_k":5}'
```
