# Production image (not needed for local work; see README for the venv setup).
FROM node:22-slim AS assets
WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm install
COPY static ./static
COPY templates ./templates
COPY apps ./apps
COPY scripts ./scripts
RUN npm run vendor && npm run build:css

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_SETTINGS_MODULE=config.settings.prod
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=assets /app/static ./static
RUN DJANGO_SECRET_KEY=build FIELD_ENCRYPTION_KEY=x python manage.py collectstatic --noinput
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
CMD ["gunicorn", "config.wsgi", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-"]
