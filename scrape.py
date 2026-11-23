"""Scrape Limitless TCG into data/cards.json: every Standard-legal print of the cards
played in the current meta."""

import html
import http.client
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

HOST = "limitlesstcg.com"
IMG = "https://limitlesstcg.nyc3.cdn.digitaloceanspaces.com/tpci/{set}/{set}_{num:0>3}_R_EN_SM.png"
OUT = Path(__file__).parent / "data" / "cards.json"
UA = "Mozilla/5.0 (compatible; playables-bot; +https://github.com/code-death/playables)"
MIN_CARDS, MIN_DECKS = 100, 5
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


def build_cards(decks, deck_cards, card_info, legal):
    """One entry per unique card (identified by its legal prints), scored by meta usage."""
    by_id = {d["id"]: d for d in decks}
    cards = {}
    for deck_id, entries in deck_cards.items():
        deck = by_id[deck_id]
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
        card["decks"] = sorted(card["decks"].values(), key=lambda d: -by_id[d["id"]]["share"])
        out.append(card)
    return sorted(out, key=lambda c: -c["score"])


_conn = None


def fetch(path):
    """GET a Limitless page over one reused HTTPS connection, 1 s apart."""
    global _conn
    for attempt in (1, 2):
        if _conn is None:
            _conn = http.client.HTTPSConnection(HOST, timeout=30)
        try:
            _conn.request("GET", path, headers={"User-Agent": UA})
            r = _conn.getresponse()
            body = r.read().decode("utf-8")
            break
        except (http.client.HTTPException, OSError):
            _conn.close()
            _conn = None  # server dropped the keep-alive connection; reconnect once
            if attempt == 2:
                raise
    time.sleep(1)
    if r.status != 200:
        raise RuntimeError(f"HTTP {r.status} for {path}")
    return body


def main():
    legal = parse_standard_list(fetch("/cards?q=f%3Astandard+d%3Alist+show%3A5000"))
    decks = parse_decks(fetch("/decks"))
    print(f"{len(legal)} legal prints, {len(decks)} decks", flush=True)
    deck_cards, card_info = {}, {}
    for i, deck in enumerate(decks, 1):
        print(f"deck {i}/{len(decks)}: {deck['name']} ({len(card_info)} card prints known)", flush=True)
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
