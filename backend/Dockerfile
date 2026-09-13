FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src

RUN pip install --no-cache-dir .

USER 65532:65532
CMD ["python", "-c", "import knowledge_system"]
