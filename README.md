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

The SQLite database is stored at `./pokestock.sqlite3` in the project base folder. Uploaded images are stored in `./media`.

## Services

- `web`: Django, server-rendered UI, admin, and HTTP endpoints.
- `worker`: Celery worker with a simple daily beat schedule for price refresh.
- `redis`: Celery broker/result backend.
- `ocr`: Local Tesseract HTTP service used by photo-assisted adding.

Only the `web` service publishes a host port (`8000`). Redis and OCR are reachable only inside the Docker network.

## Camera Add

The primary camera flow is browser-based for iOS Safari and mobile browsers. The card image is read by Tesseract.js in the browser, and only extracted text is sent to Django for candidate matching. Captured photos are not uploaded or stored by this flow.

## Set Progress

The Add Card page can browse the synced PokemonTCG set catalog and open a full checklist for any set. Use "Refresh set catalog" to fetch all available sets, then open a set to fetch every card in that checklist.

The Sets page shows progress only for sets where at least one card is owned, using official PokemonTCG set totals when catalog data is available. Open a set to page through the checklist; owned cards are full color, missing cards are grayscale, and card actions expand on click. Use "Refresh checklist" on a set detail page to refresh the full card checklist from PokemonTCG API.

## Local Development

```sh
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
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
