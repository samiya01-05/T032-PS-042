import unittest

from src.resident import is_commercial, resident_eligible
from tests.a_helpers import tag

PASS_OBJ = object()


def res(**kw):
    kw.setdefault("resident", True)
    kw.setdefault("plaza", "PLZ-01")
    kw.setdefault("dist", "5")
    return tag(**kw)


class ResidentTests(unittest.TestCase):
    def test_eligible_at_exactly_20km(self):
        self.assertTrue(resident_eligible(res(dist="20.0"), "PLZ-01", False, PASS_OBJ))

    def test_not_eligible_just_over_20km(self):
        self.assertFalse(resident_eligible(res(dist="20.01"), "PLZ-01", False, PASS_OBJ))

    def test_ec05_commercial_not_eligible(self):
        self.assertFalse(resident_eligible(res(), "PLZ-01", True, PASS_OBJ))

    def test_needs_resident_flag(self):
        self.assertFalse(resident_eligible(res(resident=False), "PLZ-01", False, PASS_OBJ))

    def test_needs_the_registered_plaza(self):
        self.assertFalse(resident_eligible(res(), "PLZ-02", False, PASS_OBJ))

    def test_needs_a_valid_pass(self):
        self.assertFalse(resident_eligible(res(), "PLZ-01", False, None))

    def test_needs_a_distance(self):
        self.assertFalse(resident_eligible(res(dist=None), "PLZ-01", False, PASS_OBJ))

    def test_is_commercial(self):
        self.assertFalse(is_commercial(tag("CAR"), "CAR"))
        self.assertTrue(is_commercial(tag("CAR"), "LCV"))              # CAR detected as LCV
        self.assertTrue(is_commercial(tag("CAR", commercial=True), "CAR"))
        self.assertTrue(is_commercial(tag("LCV"), "LCV"))


if __name__ == "__main__":
    unittest.main()
