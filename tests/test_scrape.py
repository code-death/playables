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


if __name__ == "__main__":
    unittest.main()
