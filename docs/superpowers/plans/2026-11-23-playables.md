# Playables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A GitHub Pages site showing every Standard-legal print of the cards played in the current Pokémon TCG meta, filterable by category/set/deck, refreshed weekly from Limitless TCG.

**Architecture:** `scrape.py` (stdlib only) scrapes Limitless HTML into `data/cards.json`; a single static `index.html` renders it with vanilla JS. A GitHub Action re-runs the scraper weekly or on demand and commits the JSON; Pages serves `main`.

**Tech Stack:** Python 3 stdlib (`urllib`, `re`, `html`, `json`, `unittest`), HTML/CSS/vanilla JS, GitHub Actions, GitHub Pages.

## Global Constraints

- No Python dependencies, no JS framework, no build step.
- Standard = regulation marks H, I, J (+ mark-less basic Energy). Legality comes from Limitless `f:standard`.
- Basic Energy is excluded from output (every bulk has it; not worth sorting).
- ~1 s between requests to Limitless.
- Never overwrite `data/cards.json` unless ≥ 100 cards and ≥ 5 decks were scraped.
- Credit Limitless TCG on the page.
- Repo `code-death/playables`; commits use the personal identity already set in repo-local git config.

## File Structure

```
scrape.py                     # parsers + aggregation + main()
tests/test_scrape.py          # unittest against tests/fixtures/*.html
tests/fixtures/*.html         # saved Limitless pages (already present)
data/cards.json               # output
index.html                    # UI
.github/workflows/refresh.yml # weekly + manual refresh
README.md
```

Fixtures (saved 2026-11-23): `decks.html` (/decks), `deck_cards.html` (/decks/284/cards, Dragapult ex),
`card_item.html` (/cards/POR/81 Poké Pad), `card_pokemon.html` (/cards/TWM/130 Dragapult ex),
`card_energy.html` (/cards/MEE/10 Fire Energy), `standard_list.html` (search `poke pad f:standard d:list`).

---

### Task 1: HTML parsers

**Files:**
- Create: `scrape.py`
- Test: `tests/test_scrape.py`

**Interfaces:**
- Produces:
  - `parse_decks(page: str) -> list[dict]` — `{"id": int, "name": str, "share": float}` (share in %)
  - `parse_deck_cards(page: str) -> list[dict]` — `{"set": str, "num": str, "count": float}`
  - `parse_card(page: str, set_code: str, num: str) -> dict` — `{"name", "category", "ptype", "basic", "prints": list[tuple[str,str]]}`; category ∈ Pokémon/Item/Supporter/Tool/Stadium/Energy; `ptype` only for Pokémon else None; `basic` True for basic Energy
  - `parse_standard_list(page: str) -> set[tuple[str,str]]`

- [ ] **Step 1: Write failing tests** — `tests/test_scrape.py`:

```python
import unittest
from pathlib import Path

import scrape

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


class ParseTests(unittest.TestCase):
    def test_parse_decks(self):
        decks = scrape.parse_decks(load("decks.html"))
        self.assertEqual(len(decks), 25)
        self.assertEqual(decks[0], {"id": 284, "name": "Dragapult ex", "share": 35.65})
        self.assertEqual(decks[1]["name"], "Basic Box")

    def test_parse_deck_cards(self):
        cards = scrape.parse_deck_cards(load("deck_cards.html"))
        self.assertEqual(len(cards), 40)
        self.assertIn({"set": "ASC", "num": "142", "count": 1.0}, cards)

    def test_parse_card_item_has_only_english_prints(self):
        card = scrape.parse_card(load("card_item.html"), "POR", "81")
        self.assertEqual(card["name"], "Poké Pad")
        self.assertEqual(card["category"], "Item")
        self.assertIsNone(card["ptype"])
        self.assertFalse(card["basic"])
        self.assertEqual(card["prints"], [("ASC", "198"), ("POR", "81"), ("POR", "113"), ("30C", "126")])

    def test_parse_card_pokemon(self):
        card = scrape.parse_card(load("card_pokemon.html"), "TWM", "130")
        self.assertEqual(card["name"], "Dragapult ex")
        self.assertEqual(card["category"], "Pokémon")
        self.assertEqual(card["ptype"], "Dragon")
        self.assertIn(("TWM", "130"), card["prints"])

    def test_parse_card_basic_energy(self):
        card = scrape.parse_card(load("card_energy.html"), "MEE", "10")
        self.assertEqual(card["category"], "Energy")
        self.assertTrue(card["basic"])

    def test_parse_standard_list(self):
        legal = scrape.parse_standard_list(load("standard_list.html"))
        self.assertEqual(legal, {("30C", "126"), ("POR", "81"), ("POR", "113"), ("ASC", "198")})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m unittest -v` → `ModuleNotFoundError: No module named 'scrape'`.

- [ ] **Step 3: Implement parsers** — `scrape.py`:

```python
"""Scrape Limitless TCG into data/cards.json: every Standard-legal print of the cards
played in the current meta."""

import html
import re

TRAINER_KINDS = {"Item": "Item", "Supporter": "Supporter", "Stadium": "Stadium", "Pokémon Tool": "Tool"}


def clean(fragment):
    """Strip tags, unescape entities, collapse whitespace."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_decks(page):
    rows = re.findall(r'<a href="/decks/(\d+)">(.*?)</a></td>\s*<td>\d+</td>\s*<td>([\d.]+)%</td>', page)
    return [{"id": int(i), "name": clean(name), "share": float(share)} for i, name, share in rows]


def parse_deck_cards(page):
    rows = re.findall(
        r'data-set="([A-Z0-9]+)" data-number="([^"]+)".*?<span class="card-count">([\d.]+)</span>',
        page, re.S)
    return [{"set": s, "num": n, "count": float(c)} for s, n, c in rows]


def parse_card(page, set_code, num):
    name = clean(re.search(r'<span class="card-text-name">(.*?)</span>', page, re.S).group(1))
    title = clean(re.search(r'<p class="card-text-title">(.*?)</p>', page, re.S).group(1))
    kind = [p.strip() for p in clean(re.search(r'<p class="card-text-type">(.*?)</p>', page, re.S).group(1)).split(" - ")]

    if kind[0] == "Trainer":
        category = TRAINER_KINDS.get(kind[1], kind[1])
    else:
        category = kind[0]  # "Pokémon" or "Energy"
    parts = title.split(" - ")
    ptype = parts[1] if category == "Pokémon" and len(parts) > 1 else None
    basic = category == "Energy" and len(kind) > 1 and kind[1] == "Basic Energy"

    # International prints only: the table section before the "JP. Prints" header.
    table = page.split('<table class="card-prints-versions">', 1)[1].split("</table>", 1)[0]
    table = table.split("JP. Prints", 1)[0]
    prints = []
    for row in table.split("<tr")[1:]:
        if 'class="current"' in row:
            prints.append((set_code, num))
        else:
            m = re.search(r'href="/cards/([A-Z0-9]+)/([^"]+)"', row)
            if m:
                prints.append((m.group(1), m.group(2)))
    return {"name": name, "category": category, "ptype": ptype, "basic": basic, "prints": prints}


def parse_standard_list(page):
    legal = set()
    for row in page.split("<tr data-hover")[1:]:
        m = re.search(r'href="/cards/([A-Z0-9]+)/([^"]+)"', row)
        if m:
            legal.add((m.group(1), m.group(2)))
    return legal
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m unittest -v` → 6 tests OK.

- [ ] **Step 5: Commit** — `git add scrape.py tests && git commit -m "Add Limitless HTML parsers"`

---

### Task 2: Aggregate into unique cards

**Files:**
- Modify: `scrape.py` (append)
- Test: `tests/test_scrape.py` (append class)

**Interfaces:**
- Consumes: parser outputs from Task 1.
- Produces: `build_cards(decks, deck_cards, card_info, legal) -> list[dict]` where
  `deck_cards: dict[int, list]`, `card_info: dict[tuple, dict]` keyed by `(set, num)`.
  Each output card: `{"name", "category", "ptype", "score": float, "decks": [{"id", "name", "count"}], "prints": [{"set", "num", "img"}]}`, sorted by score desc. `score = Σ share/100 × count`.
  Module constant `IMG` (format string with `{set}` / `{num}`).

- [ ] **Step 1: Write failing test** (append to `tests/test_scrape.py`, before the `__main__` block):

```python
class BuildTests(unittest.TestCase):
    def test_merges_reprints_and_drops_illegal_and_basic_energy(self):
        decks = [{"id": 1, "name": "A", "share": 50.0}, {"id": 2, "name": "B", "share": 10.0}]
        pad = {"name": "Poké Pad", "category": "Item", "ptype": None, "basic": False,
               "prints": [("POR", "81"), ("OLD", "5")]}
        fire = {"name": "Fire Energy", "category": "Energy", "ptype": None, "basic": True,
                "prints": [("MEE", "10")]}
        card_info = {("POR", "81"): pad, ("OLD", "5"): pad, ("MEE", "10"): fire}
        deck_cards = {
            1: [{"set": "POR", "num": "81", "count": 2.0}, {"set": "MEE", "num": "10", "count": 8.0}],
            2: [{"set": "OLD", "num": "5", "count": 1.0}],
        }
        legal = {("POR", "81"), ("MEE", "10")}
        cards = scrape.build_cards(decks, deck_cards, card_info, legal)
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["name"], "Poké Pad")
        self.assertAlmostEqual(c["score"], 1.1)  # 0.5*2 + 0.1*1
        self.assertEqual([d["id"] for d in c["decks"]], [1, 2])
        self.assertEqual([(p["set"], p["num"]) for p in c["prints"]], [("POR", "81")])
        self.assertTrue(c["prints"][0]["img"].endswith("/POR/POR_081_R_EN_SM.png"))
```

- [ ] **Step 2: Run, expect FAIL** — `python3 -m unittest -v` → `AttributeError: module 'scrape' has no attribute 'build_cards'`.

- [ ] **Step 3: Implement** (append to `scrape.py`; put `IMG` with the other constants at the top):

```python
IMG = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/{set}/{set}_{num:0>3}_R_EN_SM.png"


def build_cards(decks, deck_cards, card_info, legal):
    names = {d["id"]: d for d in decks}
    cards = {}
    for deck_id, entries in deck_cards.items():
        deck = names[deck_id]
        for e in entries:
            info = card_info.get((e["set"], e["num"]))
            if not info or info["basic"]:
                continue
            prints = tuple(p for p in info["prints"] if p in legal)
            if not prints:
                continue
            card = cards.setdefault(prints, {
                "name": info["name"], "category": info["category"], "ptype": info["ptype"],
                "score": 0.0, "decks": {},
                "prints": [{"set": s, "num": n, "img": IMG.format(set=s, num=n)} for s, n in prints],
            })
            card["score"] += deck["share"] / 100 * e["count"]
            d = card["decks"].setdefault(deck_id, {"id": deck_id, "name": deck["name"], "count": 0.0})
            d["count"] += e["count"]
    out = []
    for card in cards.values():
        card["score"] = round(card["score"], 4)
        card["decks"] = sorted(card["decks"].values(), key=lambda d: -names[d["id"]]["share"])
        out.append(card)
    return sorted(out, key=lambda c: -c["score"])
```

- [ ] **Step 4: Run, expect PASS** — `python3 -m unittest -v` → 7 tests OK.

- [ ] **Step 5: Commit** — `git add -A && git commit -m "Aggregate played cards across decks"`

---

### Task 3: Fetching + main, produce real data

**Files:**
- Modify: `scrape.py` (append), Create: `data/cards.json` (generated)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: `data/cards.json` = `{"updated": ISO str, "decks": [{"id","name","share"}], "cards": [...]}`; exit code 0 on success, 1 if sanity check fails.

- [ ] **Step 1: Implement** (append; move imports to top):

```python
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = "https://limitlesstcg.com"
OUT = Path(__file__).parent / "data" / "cards.json"
UA = "Mozilla/5.0 (compatible; playables-bot; +https://github.com/code-death/playables)"
MIN_CARDS, MIN_DECKS = 100, 5


def fetch(path):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode("utf-8")
    time.sleep(1)
    return body


def main():
    legal = parse_standard_list(fetch("/cards?q=f%3Astandard+d%3Alist+show%3A5000"))
    decks = parse_decks(fetch("/decks"))
    print(f"{len(legal)} legal prints, {len(decks)} decks")
    deck_cards, card_info = {}, {}
    for deck in decks:
        try:
            deck_cards[deck["id"]] = parse_deck_cards(fetch(f"/decks/{deck['id']}/cards"))
        except Exception as e:
            print(f"skip deck {deck['id']}: {e}", file=sys.stderr)
            continue
        for entry in deck_cards[deck["id"]]:
            key = (entry["set"], entry["num"])
            if key in card_info:
                continue
            try:
                info = parse_card(fetch(f"/cards/{key[0]}/{key[1]}"), *key)
            except Exception as e:
                print(f"skip card {key}: {e}", file=sys.stderr)
                continue
            for p in info["prints"]:  # reprints share one page fetch
                card_info.setdefault(p, info)
    cards = build_cards(decks, deck_cards, card_info, legal)
    print(f"{len(cards)} cards from {len(deck_cards)} decks")
    if len(cards) < MIN_CARDS or len(deck_cards) < MIN_DECKS:
        print("sanity check failed, keeping old data", file=sys.stderr)
        return 1
    OUT.parent.mkdir(exist_ok=True)
    data = {"updated": datetime.now(timezone.utc).isoformat(timespec="seconds"), "decks": decks, "cards": cards}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run tests** — `python3 -m unittest -v` → 7 OK.
- [ ] **Step 3: Live run** — `python3 scrape.py` (≈5–8 min). Expected: prints counts, exit 0, `data/cards.json` exists. Spot-check: `Poké Pad` has prints POR 81, POR 113, ASC 198, 30C 126; top card score > 1.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "Add scraper entrypoint and first data snapshot"`

---

### Task 4: The page

**Files:** Create `index.html`

**Interfaces:** Consumes `data/cards.json` (Task 3 shape).

- [ ] **Step 1: Write `index.html`** — single file; header with title + updated date; controls: search input, category chips (Pokémon/Item/Supporter/Tool/Stadium/Energy, multi-select), set chips (from data, multi-select), deck `<select>` ("All decks" + decks by share), sort `<select>` (Playability / Set & number); result count; grid of tiles (one per print; lazy `<img>`; badge with top 2 decks "Name ×N"); `<dialog>` on click with large image (`_LG` variant of the img URL), name, category/type, every deck with avg count and meta share; footer crediting Limitless with link. CSS tokens on `:root` with dark mode via `prefers-color-scheme`; grid `repeat(auto-fill, minmax(150px, 1fr))`; 16px gutters on phones. Filtering: AND across controls; OR within a chip group; empty group = all.
- [ ] **Step 2: Verify** — `python3 -m http.server 8000`, open `http://localhost:8000`, check: grid loads, each filter narrows results, deck filter shows only that deck's cards, dialog opens, phone width (375px) has no horizontal scroll.
- [ ] **Step 3: Commit** — `git add index.html && git commit -m "Add playables page"`

---

### Task 5: Refresh workflow, README, publish

**Files:** Create `.github/workflows/refresh.yml`, `README.md`

- [ ] **Step 1: Workflow**

```yaml
name: Refresh data
on:
  schedule:
    - cron: "0 3 * * 1"   # Mondays 03:00 UTC
  workflow_dispatch:
permissions:
  contents: write
jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: python -m unittest -v
      - run: python scrape.py
      - name: Commit if changed
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add data/cards.json
          git diff --cached --quiet || (git commit -m "Refresh data" && git push)
```

- [ ] **Step 2: README** — what it is, data source credit, `python3 scrape.py` to refresh locally, `python3 -m unittest` to test, Actions → "Refresh data" → Run workflow for on-demand refresh.
- [ ] **Step 3: Commit.**
- [ ] **Step 4: Publish** (needs `gh` logged in as code-death): `gh repo create code-death/playables --public --source . --push`, then enable Pages from `main` / root: `gh api -X POST repos/code-death/playables/pages -f "source[branch]=main" -f "source[path]=/"`. Verify `https://code-death.github.io/playables/` loads.
