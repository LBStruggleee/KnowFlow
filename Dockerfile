# KnowFlow backend image — local single-user deployment only.
FROM python:3.13-slim

WORKDIR /app/backend

COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/app ./app
COPY backend/__init__.py ./__init__.py

# The API serves frontend/dist when present (same-origin deployment).
COPY frontend/dist /app/frontend/dist

# Persistent state must be volume-mounted:
#   backend/data     -> SQLite database
#   backend/storage  -> uploaded files + Chroma index
#   backend/.env     -> API keys (read-only)
VOLUME ["/app/backend/data", "/app/backend/storage"]

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
