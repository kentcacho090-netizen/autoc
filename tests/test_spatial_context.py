import unittest

from automation_state import Target
from spatial_context import SpatialContextDetector, SpatialEvidence


class SpatialContextDetectorTests(unittest.TestCase):
    def setUp(self):
        self.detector = SpatialContextDetector(max_gap_pixels=120)
        self.target = Target(
            name="building_upgrade",
            center=(500, 500),
            confidence=0.95,
            source="ocr",
        )

    def test_nearby_building_authorizes_building_upgrade(self):
        evidence = [
            SpatialEvidence(
                text="Cannon",
                bounds=(450, 430, 550, 490),
                source="accessibility",
                confidence=0.98,
            )
        ]
        context = self.detector.identify(
            "building_upgrade", self.target, evidence, "home", 0.99
        )
        self.assertIsNotNone(context)
        self.assertEqual(context.object_name, "cannon")

    def test_distant_building_does_not_authorize(self):
        evidence = [
            SpatialEvidence(
                text="Cannon",
                bounds=(50, 50, 120, 100),
                source="accessibility",
                confidence=0.99,
            )
        ]
        context = self.detector.identify(
            "building_upgrade", self.target, evidence, "home", 0.99
        )
        self.assertIsNone(context)

    def test_upgrade_label_alone_is_not_object_evidence(self):
        evidence = [
            SpatialEvidence(
                text="Upgrade",
                bounds=(450, 450, 550, 520),
                source="accessibility",
                confidence=1.0,
            )
        ]
        context = self.detector.identify(
            "building_upgrade", self.target, evidence, "home", 1.0
        )
        self.assertIsNone(context)

    def test_low_confidence_object_is_rejected(self):
        evidence = [
            SpatialEvidence(
                text="Cannon",
                bounds=(450, 430, 550, 490),
                source="accessibility",
                confidence=0.60,
            )
        ]
        context = self.detector.identify(
            "building_upgrade", self.target, evidence, "home", 0.99
        )
        self.assertIsNotNone(context)
        self.assertLess(context.confidence, 0.85)


if __name__ == "__main__":
    unittest.main()
