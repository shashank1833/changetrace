FROM python:3.12-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
COPY apps apps
COPY packages packages
COPY services services
COPY workers workers
RUN pip install --no-cache-dir .
RUN useradd --create-home --uid 10001 changetrace \
    && mkdir -p /var/lib/changetrace/snapshots \
    && chown -R changetrace:changetrace /app /var/lib/changetrace
USER changetrace
EXPOSE 8000
CMD ["uvicorn", "changetrace_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
