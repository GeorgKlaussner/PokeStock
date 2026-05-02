# PokeStock

Self-hosted Django app for tracking a single-user Pokemon card collection with Cardmarket EUR pricing from PokemonTCG API data, CSV import/export, background refresh jobs, and local OCR-assisted card adding.

## Quick Start

1. Copy the environment template:

   ```sh
   cp .env.example .env
   ```

2. Edit `.env` and set `DJANGO_SECRET_KEY` and `DJANGO_SUPERUSER_PASSWORD`.

3. Start the stack:

   ```sh
   docker compose up --build
   ```

4. Open `http://localhost:8000` and log in with `DJANGO_SUPERUSER_USERNAME` and `DJANGO_SUPERUSER_PASSWORD`.

PostgreSQL data is stored in the Docker volume `postgres-data`. Uploaded images are stored in `./media`.

## Services

- `web`: Django, server-rendered UI, admin, and HTTP endpoints.
- `worker`: Celery worker with a simple daily beat schedule for price refresh.
- `db`: PostgreSQL database for Django data.
- `redis`: Celery broker/result backend.
- `ocr`: Local Tesseract HTTP service used by photo-assisted adding.

Only the `web` service publishes a host port (`8000`). PostgreSQL, Redis, and OCR are reachable only inside the Docker network.

## Camera Add

The primary camera flow sends the captured image to the internal OCR service for multilingual Tesseract recognition. The service is configured for English, German, Spanish, and Japanese by default. Captured photos from this flow are processed in memory and are not stored.

## Set Progress

The Add Card page can browse the synced PokemonTCG set catalog and open a full checklist for any set. Use "Refresh set catalog" to fetch all available sets, then open a set to fetch every card in that checklist.

The Sets page shows progress only for sets where at least one card is owned, using official PokemonTCG set totals when catalog data is available. Open a set to page through the checklist; owned cards are full color, missing cards are grayscale, and card actions expand on click. Use "Refresh checklist" on a set detail page to refresh the full card checklist from PokemonTCG API.

## Local Development

For the simplest local setup, use `docker compose up --build`. If you run Django outside Docker, start a PostgreSQL instance first and point the `POSTGRES_*` environment variables at it.

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export POSTGRES_HOST=localhost
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Run tests with:

```sh
python manage.py test
```

## CSV Import

CSV imports match cards by `card_id` first. If `card_id` is absent, rows must include exact `name`, `set_name`, and `card_number`. Ambiguous or missing rows are reported for review and are not imported.
