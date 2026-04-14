# FastAPI Tailwind Card Browser Design

## Problem statement

PaperBrain needs a web frontend for browsing and searching cards at scale. The first version should provide a masonry-style viewer with fast tabbed navigation by card type and a focused detail-reading experience.

The user-approved direction is a read-only FastAPI + Tailwind interface over PostgreSQL, with global search and tab filtering for `paper`, `person`, and `topic` cards.

## Scope

In scope:
1. Build a read-only web UI with masonry card grids.
2. Add tabs for `Paper`, `Person`, and `Topic`.
3. Implement global search with active-tab filtering.
4. Implement infinite scroll with server pagination.
5. Show card details in a right-side panel on card click.

Out of scope:
1. Create/edit/delete flows for cards.
2. Auth and user accounts.
3. Replacing CLI export pipeline behavior.
4. New card-generation logic.

## Approved design

### 1. Architecture

1. Use FastAPI as a single backend serving HTML views.
2. Use Jinja templates for server-rendered pages and partial fragments.
3. Use Tailwind CSS for layout/styling.
4. Use HTMX for progressive interactivity (tabs, search refresh, infinite-scroll append, detail panel updates).
5. Keep backend read-only and query PostgreSQL through a dedicated repository layer.

### 2. Components and routes

1. `paperbrain/web/app.py`
   - App creation, template setup, route wiring.
2. `paperbrain/web/repository.py`
   - Query helpers for type filtering, search, sorting, pagination, and lookup by id/type.
3. `paperbrain/web/schemas.py`
   - Typed view/query models (tab type, paging params, card summary/detail shapes).
4. `paperbrain/web/templates/`
   - `base.html` (shell, tabs, search box, layout frame)
   - `index.html` (initial page)
   - `_card_grid.html` (masonry fragment)
   - `_card_item.html` (single card tile)
   - `_detail_panel.html` (right-side detail content)
5. Routes:
   - `GET /` → initial page render.
   - `GET /cards` → HTMX fragment for grid refresh/append.
   - `GET /cards/{card_type}/{card_id}` → HTMX detail-panel fragment.

### 3. Data flow and UX behavior

1. Initial load:
   - `GET /` returns default-tab first page and an empty detail panel.
2. Tabs:
   - Switching tab triggers HTMX request to `/cards` with new `card_type`.
3. Search:
   - One global search input; debounced HTMX requests to `/cards`.
   - Active tab is always included in query parameters.
4. Infinite scroll:
   - `/cards` returns next page fragment with consistent page size.
   - Client appends results to existing masonry grid.
5. Detail panel:
   - Clicking a tile loads `/cards/{card_type}/{card_id}` into right panel.
6. Default ordering:
   - Sort by `updated_at DESC` (or closest existing timestamp field) for stable recent-first browsing.

### 4. Error handling and performance

1. Validate all query params (`card_type`, page params, search length bounds) and return explicit 4xx on invalid inputs.
2. Return explicit 404 for unknown card ids/types in detail route.
3. Render inline error fragments for HTMX requests; avoid silent fallbacks.
4. Enforce server-side page-size ceilings for predictable latency.
5. Add/verify indexes supporting:
   - card type filtering,
   - recent-first sort field,
   - searchable text columns used by global search.

### 5. Testing strategy

1. Repository tests:
   - card-type filtering correctness,
   - global search matching behavior,
   - pagination boundaries and ordering.
2. Route tests:
   - `GET /` initial render includes tabs/search shell.
   - `/cards` fragment rendering and param handling (`q`, `card_type`, page).
   - `/cards/{card_type}/{card_id}` detail rendering and 404 behavior.
3. Template behavior tests:
   - masonry container and card-item structure present.
   - detail-panel placeholder and loaded detail fragments render expected sections.
4. Negative tests:
   - invalid `card_type`, malformed page params, too-large page sizes produce explicit errors.

## Acceptance criteria

1. Users can browse cards in a masonry layout with tabs for Paper, Person, Topic.
2. Global search works with active-tab filtering and updates results without full-page reloads.
3. Infinite scroll loads additional pages smoothly from the backend.
4. Clicking a card loads full details into a right-side panel.
5. Routes, repository queries, and template fragments are covered by automated tests.
