import unittest
from pathlib import Path

import scrape

FIX = Path(__file__).parent / "fixtures"


def load(name):
    return (FIX / name).read_text(encoding="utf-8")


class ParseTests(unittest.TestCase):
    def test_parse_lists(self):
        # One entry per table row; the same list can appear in two rows (main() dedupes by id).
        lists = scrape.parse_lists(load("lists.html"))
        self.assertEqual(len(lists), 25)
        self.assertEqual(lists[0], {"id": 31359, "deck": "N's Zoroark"})

    def test_parse_decklist_page(self):
        cards = scrape.parse_deck_cards(load("list.html"))
        self.assertEqual(len(cards), 25)
        self.assertEqual(sum(c["count"] for c in cards), 60)
        self.assertEqual(cards[0], {"set": "JTG", "num": "97", "count": 4.0})

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


class BuildTests(unittest.TestCase):
    def test_counts_lists_merges_reprints_drops_illegal_and_basic_energy(self):
        lists = [{"id": 1, "deck": "A"}, {"id": 2, "deck": "A"}, {"id": 3, "deck": "B"}, {"id": 4, "deck": "B"}]
        pad = {"name": "Poké Pad", "category": "Item", "ptype": None, "basic": False,
               "prints": [("POR", "81"), ("POR", "113"), ("OLD", "5")]}
        fire = {"name": "Fire Energy", "category": "Energy", "ptype": None, "basic": True,
                "prints": [("MEE", "10")]}
        card_info = {("POR", "81"): pad, ("POR", "113"): pad, ("OLD", "5"): pad, ("MEE", "10"): fire}
        list_cards = {
            1: [{"set": "POR", "num": "81", "count": 3.0}, {"set": "POR", "num": "113", "count": 1.0},
                {"set": "MEE", "num": "10", "count": 8.0}],
            2: [{"set": "POR", "num": "81", "count": 2.0}],
            3: [{"set": "OLD", "num": "5", "count": 2.0}],
            4: [{"set": "MEE", "num": "10", "count": 10.0}],
        }
        legal = {("POR", "81"), ("POR", "113"), ("MEE", "10")}
        cards = scrape.build_cards(lists, list_cards, card_info, legal)
        self.assertEqual(len(cards), 1)
        c = cards[0]
        self.assertEqual(c["name"], "Poké Pad")
        self.assertEqual(c["lists"], 3)             # lists 1, 2, 3 (two prints in list 1 count once)
        self.assertEqual(c["pct"], 75.0)
        self.assertAlmostEqual(c["avg"], 8 / 3, places=2)  # (4 + 2 + 2) / 3
        self.assertEqual(c["decks"], [{"name": "A", "lists": 2, "avg": 3.0}, {"name": "B", "lists": 1, "avg": 2.0}])
        self.assertEqual([(p["set"], p["num"]) for p in c["prints"]], [("POR", "81"), ("POR", "113")])
        self.assertTrue(c["prints"][0]["img"].endswith("/POR/POR_081_R_EN_SM.png"))


if __name__ == "__main__":
    unittest.main()
