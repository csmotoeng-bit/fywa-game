"""Offline content sanity checks for the FYWA word games."""
import random
import unittest

from game_state.word_content import CLUELESS_WORDS, DOTS_PUZZLES, FORBIDDEN_CARDS


class WordPackTests(unittest.TestCase):
    def test_clueless_is_large_unique_and_phone_friendly(self):
        self.assertGreaterEqual(len(CLUELESS_WORDS), 400)
        self.assertEqual(len(CLUELESS_WORDS), len(set(CLUELESS_WORDS)))
        self.assertTrue(all(1 <= len(word) <= 24 for word in CLUELESS_WORDS))
        for example in ("NAN'S ASHES", "TAX FRAUD", "BINS ON FIRE", "FAKE PASSPORT"):
            self.assertIn(example, CLUELESS_WORDS)
        for seed in range(100):
            board = random.Random(seed).sample(CLUELESS_WORDS, 25)
            self.assertEqual(len(set(board)), 25)

    def test_connections_every_board_has_four_unique_valid_groups(self):
        self.assertGreaterEqual(len(DOTS_PUZZLES), 50)
        for board in DOTS_PUZZLES:
            self.assertEqual(len(board), 4)
            words = []
            for label, group in board:
                self.assertTrue(label.strip())
                self.assertEqual(len(group), 4)
                self.assertEqual(len(set(group)), 4)
                words.extend(group)
            self.assertEqual(len(words), 16)
            self.assertEqual(len(set(words)), 16)
            self.assertTrue(all(1 <= len(word) <= 24 for word in words))

    def test_forbidden_words_pack_is_unchanged(self):
        self.assertEqual(len(FORBIDDEN_CARDS), 81)


if __name__ == "__main__":
    unittest.main()
