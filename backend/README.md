# KnowFlow Backend

FastAPI backend for KnowFlow（知汇）.

## Run

```powershell
cd D:\bruce\KnowFlow\backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
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
EMBEDDING_PROVIDER=dashscope
EMBEDDING_MODEL=text-embedding-v3
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_MODEL=qwen-plus
```

## Check

- Health: http://127.0.0.1:8000/api/health
- Swagger: http://127.0.0.1:8000/docs

真实语义 embedding 使用与模型名绑定的独立 Chroma collection。修改 embedding 模型后，请调用 `POST /api/kbs/{kb_id}/rebuild-index` 重建该知识库索引。

## Quality

```powershell
$env:PYTHONPATH = "."
pytest tests -q
ruff check .
ruff format --check .
pip-audit -r requirements.txt --ignore-vuln PYSEC-2026-311
```

`PYSEC-2026-311` 当前没有上游修复版本，影响 Chroma 的服务端鉴权场景。本项目只使用进程内的本地 `PersistentClient`，且后端默认仅监听 `127.0.0.1`；不得把 Chroma 作为独立公网服务暴露。

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
  -Form @{ file = Get-Item "path\to\your\document.md" }
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
