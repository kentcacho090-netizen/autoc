import unittest

from action_verification import PostActionVerifier
from ui_targets import UITarget


class ActionVerificationTests(unittest.TestCase):
    def target(self, text="Upgrade", x=100, y=200, width=80, height=40, confidence=0.95):
        return UITarget("upgrade", text, x, y, width, height, confidence, "ocr")

    def test_disappeared_target_is_verified(self):
        before = self.target()
        verifier = PostActionVerifier(lambda _image, _name: None)
        result = verifier.verify(before, "after.png")
        self.assertTrue(result.verified)

    def test_unchanged_target_is_rejected(self):
        before = self.target()
        verifier = PostActionVerifier(lambda _image, _name: self.target())
        result = verifier.verify(before, "after.png")
        self.assertFalse(result.verified)

    def test_changed_target_is_verified(self):
        before = self.target()
        after = self.target(text="Cancel", confidence=0.70)
        verifier = PostActionVerifier(lambda _image, _name: after)
        result = verifier.verify(before, "after.png")
        self.assertTrue(result.verified)

    def test_distant_target_is_not_the_same_target(self):
        before = self.target()
        after = self.target(x=700, y=100)
        verifier = PostActionVerifier(lambda _image, _name: after)
        result = verifier.verify(before, "after.png")
        self.assertTrue(result.verified)

    def test_missing_post_screenshot_is_rejected(self):
        before = self.target()
        verifier = PostActionVerifier(lambda _image, _name: None)
        result = verifier.verify(before, "")
        self.assertFalse(result.verified)


if __name__ == "__main__":
    unittest.main()
