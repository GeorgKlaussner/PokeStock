FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sh", "-c", "gunicorn pokestock_project.wsgi:application --bind 0.0.0.0:8000 --worker-class gthread --workers \"${WEB_CONCURRENCY:-2}\" --threads \"${GUNICORN_THREADS:-4}\" --timeout \"${GUNICORN_TIMEOUT:-60}\" --access-logfile - --error-logfile - --access-logformat '%(h)s %(r)s %(s)s %(M)sms'"]
