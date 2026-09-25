# Two stages because the frontend needs Node to build but nothing at runtime: the
# API serves the compiled bundle itself, which keeps everything on one origin and
# means one URL to hand out and no CORS to configure.

FROM node:22-slim AS frontend
WORKDIR /build
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build


FROM python:3.13-slim
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
# The base character the garment layers are aligned to; the pipeline measures every
# new avatar against it, so it has to ship with the image.
COPY assets/avatar/ ./assets/avatar/
COPY --from=frontend /build/dist ./frontend/dist

# Files live in the bucket once STORAGE_BACKEND=s3, but the pipeline still writes
# scratch images while it works, and the container disk is fine for that.
RUN mkdir -p media/tmp

EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --app-dir backend"]
