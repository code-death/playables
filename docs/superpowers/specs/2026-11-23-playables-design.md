# Playables — design

**Goal:** a static page that shows the Pokémon TCG cards actually played in the current
Standard meta (regulation marks H, I, J), with every legal English print as an image, so
people can pull playables out of their bulk.

**Deploy:** GitHub Pages, repo `code-death/playables`. Keep it as simple as possible: no
framework, no build step, no Python dependencies.

## Data source (Limitless TCG, plain HTML scraping)

- `https://limitlesstcg.com/decks` — metagame archetypes: link `/decks/{id}`, name, share %.
- `https://limitlesstcg.com/decks/{id}/cards` — cards an archetype plays (links
  `/cards/{SET}/{NUM}`) with average copies per list.
- `https://limitlesstcg.com/cards/{SET}/{NUM}` — card page: name, card type/stage,
  Pokémon type, regulation mark and the "Int. Prints" list (all English prints of the same
  card, i.e. reprints with identical text).
- `https://limitlesstcg.com/cards?q=f:standard d:list` (paged) — the set of Standard-legal
  prints. Verified 2026-11-23: 3,596 prints = H 1,303 + I 1,277 + J 798 + mark-less basic
  Energy. Used to drop non-legal prints from a card's print list.
- Image URLs follow `https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/{SET}/{SET}_{NNN}_R_EN_{SIZE}.png`.

The browser cannot fetch Limitless directly (CORS), so data is pre-scraped into JSON.

## Files

```
scrape.py                         # stdlib only; writes data/cards.json
data/cards.json                   # committed; read by the page
index.html                        # whole UI: HTML + CSS + vanilla JS
.github/workflows/refresh.yml     # weekly cron + workflow_dispatch: scrape, commit
```

Pages serves the `main` branch root.

## scrape.py

1. Fetch `/decks`, parse archetypes (id, name, share).
2. For each archetype fetch `/decks/{id}/cards`, parse (card link, average count).
3. For each unique played card link fetch the card page once (cache by link); parse name,
   category, Pokémon type and its Int. Prints. Keep prints that are in the Standard-legal set.
4. Group by unique card (the print set identifies it). Output per card:
   `name, category, ptype, score, decks[{id,name,count}], prints[{set,num,img}]`
   where `score = Σ(deck share × avg count)`.
5. Write `{updated, decks[], cards[]}` to `data/cards.json`.

Politeness/robustness: ~1 s between requests, User-Agent set, a failed page is logged and
skipped. Only overwrite the JSON when the run is sane (≥ 100 cards and ≥ 5 decks); otherwise
exit non-zero and leave the old file.

Categories: Pokémon, Item, Supporter, Tool, Stadium, Energy.

## index.html

- Grid of card images — one tile per legal print (bulk sorting matches the physical print).
- Filters: category chips, set chips, deck dropdown, name search. Combined with AND.
- Sort: playability score (default) or set/number.
- Tile badge: top decks with counts (e.g. "Dragapult ex ×3"); click opens a detail panel
  listing all decks that play it.
- Footer: "Data from Limitless TCG · updated <date>" with link.
- Images lazy-loaded; works on phone width.

## refresh.yml

Triggers: `schedule` (weekly) and `workflow_dispatch`. Steps: checkout, setup Python,
`python scrape.py`, commit `data/cards.json` if changed, push. Pages redeploys on push.

## Out of scope (later)

Prices in UI, Japanese prints, Expanded, browsing all 3,596 legal cards.

## Testing

`scrape.py` parsing functions are tested against saved HTML fixtures (`tests/fixtures/`)
with `unittest` (stdlib). The page is checked manually in a browser against the real JSON.

## Revision 2026-11-23 — decklists instead of meta archetypes

Source switched from `/decks` (25 archetypes, average counts) to the latest 500 Standard decklists
(`/decks/lists?format=standard&show=500&page=N`, then `/decks/list/{id}`; same card markup). Lists
can repeat across rows — dedupe by id. Per card: `lists`, `pct` (of decklists), `avg` copies when
played, `decks[{name, lists, avg}]` by archetype name. Default sort: most lists. Fetching uses 4
parallel keep-alive connections (Limitless latency flat to 4, ~3× worse at 8; no rate-limit headers
seen) with backoff on 429/5xx, capped at 10 req/s overall (uncapped, GitHub runners hit ~50 req/s). Full run ≈ 90 s on Actions, ≈ 2 min from India.
