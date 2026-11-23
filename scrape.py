"""Scrape Limitless TCG into data/cards.json: every Standard-legal print of the cards
played in the most recent Standard tournament decklists."""

import html
import http.client
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

HOST = "limitlesstcg.com"
IMG = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/{set}/{set}_{num:0>3}_R_EN_SM.png"
OUT = Path(__file__).parent / "data" / "cards.json"
UA = "Mozilla/5.0 (compatible; playables-bot; +https://github.com/code-death/playables)"
LISTS = 500
# Limitless latency stays flat at 4 parallel connections and triples at 8 (measured
# 2026-11-23). From GitHub runners 4 connections reach ~50 req/s, so also cap the overall
# rate to keep the load polite.
WORKERS = 4
MAX_RATE = 10  # requests per second, across all threads
MIN_CARDS, MIN_LISTS = 100, 100
TRAINER_KINDS = {"Item": "Item", "Supporter": "Supporter", "Stadium": "Stadium", "Pokémon Tool": "Tool"}


def clean(fragment):
    """Strip tags, unescape entities, collapse whitespace."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def parse_lists(page):
    """Decklist rows on /decks/lists: list id + archetype name."""
    rows = re.findall(r'<a href="/decks/list/(\d+)">([^<]+)<span class="annotation">by', page)
    return [{"id": int(i), "deck": clean(name)} for i, name in rows]


def parse_deck_cards(page):
    """Cards on a decklist page (/decks/list/{id}) or archetype page (/decks/{id}/cards)."""
    rows = re.findall(
        r'data-set="([A-Z0-9]+)" data-number="([^"]+)".*?<span class="card-count">([\d.]+)</span>',
        page, re.S)
    return [{"set": s, "num": n, "count": float(c)} for s, n, c in rows]


def parse_card(page, set_code, num):
    name = clean(re.search(r'<span class="card-text-name">(.*?)</span>', page, re.S).group(1))
    title = clean(re.search(r'<p class="card-text-title">(.*?)</p>', page, re.S).group(1))
    kind = clean(re.search(r'<p class="card-text-type">(.*?)</p>', page, re.S).group(1)).split(" - ")

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


def build_cards(lists, list_cards, card_info, legal):
    """One entry per unique card (identified by its legal prints), with how many of the
    decklists play it and how many copies, overall and per archetype."""
    deck_of = {l["id"]: l["deck"] for l in lists}
    total = len(list_cards)
    cards = {}
    for list_id, entries in list_cards.items():
        played = {}  # same card can appear as two prints in one list: sum them
        for e in entries:
            info = card_info.get((e["set"], e["num"]))
            if not info or info["basic"]:
                continue
            prints = tuple(p for p in info["prints"] if p in legal)
            if prints:
                played[prints] = played.get(prints, 0) + e["count"]
                cards.setdefault(prints, {
                    "name": info["name"], "category": info["category"], "ptype": info["ptype"],
                    "lists": 0, "copies": 0.0, "decks": {},
                    "prints": [{"set": s, "num": n, "img": IMG.format(set=s, num=n)} for s, n in prints],
                })
        for prints, count in played.items():
            card = cards[prints]
            card["lists"] += 1
            card["copies"] += count
            d = card["decks"].setdefault(deck_of[list_id], {"name": deck_of[list_id], "lists": 0, "copies": 0.0})
            d["lists"] += 1
            d["copies"] += count
    out = []
    for card in cards.values():
        card["pct"] = round(100 * card["lists"] / total, 1)
        card["avg"] = round(card.pop("copies") / card["lists"], 2)
        for d in card["decks"].values():
            d["avg"] = round(d.pop("copies") / d["lists"], 2)
        card["decks"] = sorted(card["decks"].values(), key=lambda d: (-d["lists"], d["name"]))
        out.append(card)
    return sorted(out, key=lambda c: (-c["lists"], -c["avg"], c["name"]))


_local = threading.local()
_rate_lock = threading.Lock()
_next_slot = 0.0


def wait_turn():
    """Space request starts at least 1/MAX_RATE seconds apart across threads."""
    global _next_slot
    with _rate_lock:
        now = time.monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + 1 / MAX_RATE
    time.sleep(slot - now)


def fetch(path):
    """GET a Limitless page over this thread's keep-alive connection, retrying with
    backoff on dropped connections, 429 and 5xx."""
    for attempt in range(4):
        if attempt:
            time.sleep(5 * 2 ** attempt)
        conn = getattr(_local, "conn", None) or http.client.HTTPSConnection(HOST, timeout=30)
        _local.conn = conn
        wait_turn()
        try:
            conn.request("GET", path, headers={"User-Agent": UA})
            r = conn.getresponse()
            body = r.read().decode("utf-8")
        except (http.client.HTTPException, OSError):
            conn.close()
            _local.conn = None
            continue
        if r.status == 200:
            return body
        if r.status != 429 and r.status < 500:
            raise RuntimeError(f"HTTP {r.status} for {path}")
        print(f"HTTP {r.status} for {path}, backing off", file=sys.stderr, flush=True)
    raise RuntimeError(f"gave up on {path}")


def fetch_many(jobs):
    """Fetch (path, parse) jobs in parallel; returns parse results in order, None on failure."""
    def one(job):
        path, parse = job
        try:
            return parse(fetch(path))
        except Exception as e:
            print(f"skip {path}: {e}", file=sys.stderr, flush=True)
            return None
    with ThreadPoolExecutor(WORKERS) as ex:
        return list(ex.map(one, jobs))


def main():
    legal = parse_standard_list(fetch("/cards?q=f%3Astandard+d%3Alist+show%3A5000"))

    lists, seen, page = [], set(), 1
    while len(lists) < LISTS:
        rows = parse_lists(fetch(f"/decks/lists?format=standard&show=500&page={page}"))
        if not rows:
            break
        for row in rows:
            if row["id"] not in seen and len(lists) < LISTS:
                seen.add(row["id"])
                lists.append(row)
        page += 1
    print(f"{len(legal)} legal prints, {len(lists)} decklists", flush=True)

    pages = fetch_many([(f"/decks/list/{l['id']}", parse_deck_cards) for l in lists])
    list_cards = {l["id"]: cards for l, cards in zip(lists, pages) if cards}
    print(f"fetched {len(list_cards)} decklists", flush=True)

    # Fetch each card page once; a page lists all reprints, so skip keys it already covered.
    keys = list(dict.fromkeys((e["set"], e["num"]) for cards in list_cards.values() for e in cards))
    card_info = {}
    while True:
        pending = [k for k in keys if k not in card_info][:WORKERS * 4]
        if not pending:
            break
        infos = fetch_many([(f"/cards/{s}/{n}", lambda page, s=s, n=n: parse_card(page, s, n))
                            for s, n in pending])
        for key, info in zip(pending, infos):
            for p in (info["prints"] if info else [key]):
                card_info.setdefault(p, info)
        print(f"card pages: {sum(1 for k in keys if k in card_info)}/{len(keys)}", flush=True)
    card_info = {k: v for k, v in card_info.items() if v}

    cards = build_cards(lists, list_cards, card_info, legal)
    print(f"{len(cards)} cards from {len(list_cards)} decklists", flush=True)
    if len(cards) < MIN_CARDS or len(list_cards) < MIN_LISTS:
        print("sanity check failed, keeping old data", file=sys.stderr)
        return 1

    decks = {}
    for l in lists:
        if l["id"] in list_cards:
            decks[l["deck"]] = decks.get(l["deck"], 0) + 1
    data = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "lists": len(list_cards),
        "decks": [{"name": n, "lists": c} for n, c in sorted(decks.items(), key=lambda x: (-x[1], x[0]))],
        "cards": cards,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
