import os
import shutil
import tempfile
import unittest
from decimal import Decimal

from src.loader import load_state
from src.state import DataError

SAMPLE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sample_data")

FILES = {
    "banks.csv": "bank_id,bank_name\nBNK-01,Test Bank\n",
    "plazas.csv": "plaza_id,plaza_name,highway,nearest_plaza_km\nPLZ-01,Base,NH-75,38.0\n",
    "plaza_tariffs.csv": ("plaza_id,vehicle_class,single_journey_fee,monthly_pass_fee\n"
                          "PLZ-01,CAR,85.00,2833.33\n"),
    "tags.csv": ("tag_id,vehicle_no,vehicle_class,commercial,issuer_bank,balance,status,"
                 "resident_flag,resident_plaza_id,resident_distance_km\n"
                 "AAA,KA01,CAR,false,BNK-01,600.00,ACTIVE,false,,\n"),
    "monthly_passes.csv": ("pass_id,tag_id,plaza_id,pass_type,purchase_date,valid_to,"
                           "journeys_total,journeys_used_opening,amount_paid\n"),
    "avc_history.csv": "tag_id,txn_ts,plaza_id,detected_class\n",
}


def write_files(folder, overrides=None):
    files = dict(FILES)
    files.update(overrides or {})
    for name, text in files.items():
        with open(os.path.join(folder, name), "w", encoding="utf-8") as f:
            f.write(text)


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_minimal_valid_data(self):
        write_files(self.tmp)
        s = load_state(self.tmp)
        self.assertEqual(list(s.banks), ["BNK-01"])
        self.assertEqual(s.tags["AAA"].balance, Decimal("600.00"))
        self.assertIsNone(s.tags["AAA"].resident_plaza_id)
        self.assertEqual(s.fee_for("PLZ-01", "CAR"), Decimal("85.00"))
        self.assertEqual(s.opening_balances["AAA"], Decimal("600.00"))

    def test_missing_file(self):
        write_files(self.tmp)
        os.remove(os.path.join(self.tmp, "banks.csv"))
        with self.assertRaises(DataError):
            load_state(self.tmp)

    def test_missing_column(self):
        write_files(self.tmp, {"banks.csv": "bank_id\nBNK-01\n"})
        with self.assertRaises(DataError):
            load_state(self.tmp)

    def test_unknown_bank_status_and_bool(self):
        bad_bank = FILES["tags.csv"].replace("BNK-01,600", "BNK-99,600")
        write_files(self.tmp, {"tags.csv": bad_bank})
        with self.assertRaises(DataError):
            load_state(self.tmp)
        write_files(self.tmp, {"tags.csv": FILES["tags.csv"].replace("ACTIVE", "WEIRD")})
        with self.assertRaises(DataError):
            load_state(self.tmp)
        write_files(self.tmp, {"tags.csv": FILES["tags.csv"].replace(",false,BNK", ",maybe,BNK")})
        with self.assertRaises(DataError):
            load_state(self.tmp)

    def test_pass_with_unknown_tag(self):
        passes = (FILES["monthly_passes.csv"]
                  + "MPS-1,ZZZ,PLZ-01,COMMUTER_50,2026-09-20,2026-10-19,50,49,2500.00\n")
        write_files(self.tmp, {"monthly_passes.csv": passes})
        with self.assertRaises(DataError):
            load_state(self.tmp)

    @unittest.skipUnless(os.path.isdir(SAMPLE), "sample_data folder not present")
    def test_real_sample_pack(self):
        s = load_state(SAMPLE)
        self.assertEqual((len(s.banks), len(s.plazas), len(s.tariffs), len(s.tags),
                          len(s.passes), len(s.avc_history)), (4, 3, 18, 40, 8, 2))
        lcv = next(t for t in s.tags.values() if t.vehicle_no == "KA03KJ9166")
        self.assertEqual(lcv.balance, Decimal("140.00"))                  # EC-03 tag
        resident = next(t for t in s.tags.values() if t.vehicle_no == "TN29MC1445")
        self.assertEqual(resident.resident_distance_km, Decimal("20.0"))  # exactly 20 km
        mps1 = next(p for p in s.passes if p.pass_id == "MPS-001")
        self.assertEqual((mps1.journeys_total, mps1.journeys_used), (50, 49))  # EC-02 pass
        mps6 = next(p for p in s.passes if p.pass_id == "MPS-006")
        self.assertIsNone(mps6.journeys_total)                            # resident pass


if __name__ == "__main__":
    unittest.main()
