# PokeStock Plan And Implementation Notes

This file records the intended product direction, implementation choices, and recent changes so a future agent can understand what was built and why.

## Product Goal

PokeStock is a self-hosted, single-user Pokemon card collection app. It should make it fast to add owned cards, track collection value, and explore set completion progress.

The app is optimized for private home-server use, not public SaaS multi-tenancy.

## Core Architecture Choices

- Use a Django monolith with server-rendered pages.
- Use PostgreSQL as the application database through Docker Compose.
- Run locally or through Docker Compose with these services:
  - `web`: Django app.
  - `worker`: Celery worker/beat.
  - `db`: PostgreSQL database.
  - `redis`: broker/cache.
  - `ocr`: local OCR service for camera and upload flows.
- Only `web` should publish a host port. PostgreSQL, Redis, and OCR must remain reachable only through the internal Docker network.
- The app Dockerfile should not declare `EXPOSE 8000`; Compose is the source of truth for publishing only the `web` service.
- In the current self-hosted v1 stack, Django serves static assets in `DEBUG` mode via `staticfiles_urlpatterns()`. There is no Nginx or WhiteNoise layer yet.
- Do not commit secrets. Use `.env.example` for configuration shape.
- Require one local admin login. No public registration or multi-user tenancy in v1.

## Pricing And API Choices

- Card metadata and pricing come from PokemonTCG API.
- Use PokemonTCG API Cardmarket EUR fields for pricing.
- Direct Cardmarket API integration is intentionally out of scope for v1 because new Cardmarket API applications are currently not generally accepted.
- PokemonTCG API calls intentionally ignore SSL certificate verification in this app because the user was hitting local SSL errors and requested this behavior.
- Price selection behavior:
  - Prefer average sold prices (`averageSellPrice`, or reverse-holo average fields for reverse holo variants).
  - Fall back to trend prices, then low prices, when average fields are missing.
  - Owned-row values apply local modifiers for condition and non-English language data; German cards use `germanProLow` when it is lower than the generic average.
  - Missing prices are excluded from totals and shown as unavailable.

Relevant code:
- `collection/services/pokemon_tcg.py`
- `collection/services/pricing.py`

## Domain Model Choices

Card metadata and ownership are separate.

`CardMetadata` stores upstream card data:
- PokemonTCG id.
- name.
- set id/name/series.
- card number.
- rarity.
- images.
- release date.
- Cardmarket URL.
- latest price payload and selected price fields.

`OwnedCard` stores owned copies:
- card.
- variant/finish.
- language.
- condition.
- quantity.
- purchase details.
- notes.

`SetMetadata` was added to store the official PokemonTCG set catalog:
- external set id.
- name and series.
- printed total and total.
- release date.
- logo/symbol URLs.
- API sync metadata.

Why `SetMetadata` exists:
- Set progress was previously wrong when only cached cards were counted.
- Example: Scarlet & Violet 151 showed 100% when only one cached card existed.
- Progress now uses official set totals when available.

Relevant code:
- `collection/models.py`
- `collection/migrations/0002_setmetadata.py`
- `collection/services/set_progress.py`

## Set Catalog And Progress Behavior

There are two different set browsing surfaces:

- `/add/`
  - Shows all synced PokemonTCG sets.
  - Used to browse available sets and add cards from any set.
  - Has a "Refresh set catalog" action.

- `/sets/`
  - Shows only sets with at least one owned card.
  - Used to track the current collection progress.
  - This is intentionally not a full catalog view.

Set detail/checklist behavior:
- Opening a set renders cached checklist data immediately. If the checklist is incomplete, the page queues a Celery refresh instead of blocking the request on PokemonTCG API.
- Owned cards are shown in full color.
- Missing cards are shown in grayscale.
- Cards are paginated at 48 per page.
- Card actions are hidden until the card is expanded by click/tap.

This split exists because:
- The user wants to see all available sets and cards while adding.
- The progress page should stay focused on sets the user actually owns.
- Full sets like 151 have 207 cards, so pagination avoids huge pages.
- Hidden actions keep dense set grids usable on desktop and iOS.

Relevant code:
- `collection/views.py`
- `collection/templates/collection/add_search.html`
- `collection/templates/collection/add_set_cards.html`
- `collection/templates/collection/sets_index.html`
- `collection/templates/collection/set_detail.html`
- `collection/templates/collection/includes/pagination.html`
- `static/pokestock.css`

## Camera Add Behavior

The preferred camera flow uses the internal OCR service:
- User captures/selects a photo via `<input type="file" accept="image/*" capture="environment">`.
- Django forwards the image bytes to the OCR service.
- Tesseract is configured for English, German, Spanish, and Japanese.
- The image is not uploaded or stored by this flow.

This was built to make mobile/iOS card adding faster while respecting the user's request not to store photos.

This keeps OCR fully inside the compose stack while avoiding persisted camera photos.

Relevant code:
- `collection/templates/collection/camera_add.html`
- `static/camera_add.js`
- `collection/views.py` `camera_candidates`
- `collection/tests/test_camera_views.py`

## Local Data Notes

The PostgreSQL volume is intentionally not tracked by git. The move from SQLite was treated as a fresh-database switch; existing local SQLite data was not migrated.

## UI Direction

The user explicitly asked for modern desktop usage and mobile/iOS focus.

Current UI choices:
- Server-rendered responsive Django templates.
- Sidebar desktop navigation.
- Bottom mobile tab bar.
- Light, work-focused palette.
- No giant black form surfaces.
- Compact cards, stats, and grids.
- Grayscale images communicate missing cards.
- Expandable cards keep actions out of the default grid.

Keep future UI changes consistent with this direction.

## Verification Commands

Use Docker Compose so tests run against PostgreSQL:

```sh
docker compose config --quiet
docker compose run --rm web python manage.py check
docker compose run --rm web python manage.py test
docker compose run --rm web python manage.py makemigrations --check --dry-run
```

Expected current state after the latest changes:
- Full test suite passes.
- No pending migrations.
- Docker Compose config validates.

## Known Tradeoffs And Follow-Ups

- Pagination is fixed at 48 set cards and 50 collection rows per page. If the user wants control, add a page-size selector.
- Quick add uses default details (`en`, normal, near mint) and increments an existing matching default row. This is fast but may need user-configurable defaults.
- The legacy OCR upload flow still stores uploaded images because it is separate from the no-storage browser camera flow.
- Set catalog refresh is manual from the UI. A scheduled background refresh could be added later.
