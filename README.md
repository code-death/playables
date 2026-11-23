# Standard Playables

Every Standard-legal print (regulation marks H, I, J) of the Pokémon TCG cards played in the
current meta — so you can pull playables out of your bulk.

Live: https://code-death.github.io/playables/

## How it works

- `scrape.py` reads [Limitless TCG](https://limitlesstcg.com/decks): the meta decks, the cards each
  deck plays (average copies), and every English print of those cards, keeping only Standard-legal
  prints. Output: `data/cards.json`. Python stdlib only.
- `index.html` is the whole site: filters by type, set, deck and name.
- A GitHub Action (`Refresh data`) re-scrapes every Monday. To refresh now:
  Actions → Refresh data → Run workflow.

## Local

```sh
python3 -m unittest      # parser tests against saved pages in tests/fixtures
python3 scrape.py        # refresh data/cards.json (~5–8 min, 1 request/sec)
python3 -m http.server   # then open http://localhost:8000
```

Card data and images © The Pokémon Company; data via Limitless TCG. Not affiliated with either.
