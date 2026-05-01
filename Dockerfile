FROM python:3.12-slim

# easyocr (via opencv) needs libgl + glib + libgomp at runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# Install uv (fast Python package manager)
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Install dependencies into /app/.venv from the lockfile (reproducible).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

COPY app ./app
COPY scripts ./scripts
COPY forbidden_ingredients.csv product_index.csv ./
COPY texts ./texts
COPY pdfs ./pdfs
COPY images ./images

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1
EXPOSE 8000

# easyocr downloads ~100MB of model weights on first request.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
