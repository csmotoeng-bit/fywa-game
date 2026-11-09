"""Regression tests for host-only Extreme word selection and private spymaster key."""
import os
import unittest
os.environ.setdefault("FYWA_ASYNC_MODE", "threading")
import test_multiplayer as suite
from game_state.word_content import CLUELESS_WORDS, CLUELESS_EXTREME_WORDS, validate_content


class ExtremeModeTests(unittest.TestCase):
    setUp = suite.MultiplayerTests.setUp
    tearDown = suite.MultiplayerTests.tearDown
    select = suite.MultiplayerTests.select
    start = suite.MultiplayerTests.start
    get_party_view = suite.MultiplayerTests.get_party_view
    def test_default_off_and_host_can_toggle(self):
        self.select("clueless")
        self.assertFalse(self.room["settings"]["clueless_extreme"])
        self.start()
        self.assertFalse(self.room["party"]["extreme"])
        self.assertTrue(set(self.room["party"]["words"]).issubset(set(CLUELESS_WORDS)))

    def test_host_only_toggle_and_extreme_board(self):
        self.select("clueless")
        self.sockets[1].emit("hub_settings", {"clueless_extreme": True})
        self.assertFalse(self.room["settings"]["clueless_extreme"])
        self.sockets[0].emit("hub_settings", {"clueless_extreme": "yes"})
        self.assertFalse(self.room["settings"]["clueless_extreme"])
        self.sockets[0].emit("hub_settings", {"clueless_extreme": True})
        self.assertTrue(self.room["settings"]["clueless_extreme"])
        self.start()
        board=self.room["party"]["words"]
        self.assertEqual(len(board), 25)
        self.assertEqual(len(set(board)), 25)
        self.assertTrue(all(len(word.split()) == 1 for word in board))
        self.assertEqual(len(set(board) & (set(CLUELESS_EXTREME_WORDS)-set(CLUELESS_WORDS))), 15)
        self.assertTrue(self.get_party_view(1)["extreme"])
        self.sockets[0].emit("hub_settings", {"clueless_extreme": False})
        self.assertTrue(self.room["settings"]["clueless_extreme"])
        self.assertTrue(self.room["party"]["extreme"])

    def test_content(self):
        validate_content()
        for word in ("HITLER", "JEWS", "TIANANMEN", "DILDO"):
            self.assertIn(word, CLUELESS_EXTREME_WORDS)


if __name__ == "__main__":
    unittest.main()
