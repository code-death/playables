# Standard Playables

Every Standard-legal print (regulation marks H, I, J) of every Pokémon TCG card played in the
latest 500 Standard tournament decklists — so you can pull playables out of your bulk.

Live: https://code-death.github.io/playables/

## How it works

- `scrape.py` reads [Limitless TCG](https://limitlesstcg.com/decks/lists?format=standard): the latest
  500 Standard decklists, the cards in each, and every English print of those cards, keeping only
  Standard-legal prints. Each card gets "% of lists" and average copies, overall and per archetype.
  Output: `data/cards.json`. Python stdlib only; 4 parallel connections (Limitless's latency stays
  flat up to 4, measured), backoff on 429/5xx.
- `index.html` is the whole site: filters by type, set, deck and name.
- A GitHub Action (`Refresh data`) re-scrapes every Monday. To refresh now:
  Actions → Refresh data → Run workflow.

## Local

```sh
python3 -m unittest      # parser tests against saved pages in tests/fixtures
python3 scrape.py        # refresh data/cards.json (~2–3 min)
python3 -m http.server   # then open http://localhost:8000
```

Card data and images © The Pokémon Company; data via Limitless TCG. Not affiliated with either.
