# School Virtual Library - production image.
#
# The French catalogs are COMMITTED as .mo, so building the image needs no
# GNU gettext and no Babel. Since the deploy service accounts for the planned
# pgvector search, the runtime only needs PostgreSQL (pgvector image).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings

WORKDIR /app

# Requirements first so dependency layers cache across rebuilds.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Web: served by gunicorn, static via Whitenoise (already collected).
EXPOSE 8000
CMD ["sh", "-c", "python manage.py collectstatic --noinput && \
     gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 \
     --timeout 60 --access-logfile - --error-logfile -"]