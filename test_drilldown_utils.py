import unittest

import pandas as pd

from drilldown_utils import ALL_OPTION, drilldown_options, product_monitor_selection


class DrilldownUtilsTest(unittest.TestCase):
    def setUp(self):
        self.dims = pd.DataFrame([
            {"item20": "반도체", "middle_category": "메모리반도체", "product": "DRAM"},
            {"item20": "반도체", "middle_category": "메모리반도체", "product": "NAND"},
            {"item20": "반도체", "middle_category": "시스템반도체", "product": "AP"},
            {"item20": "자동차", "middle_category": "승용차", "product": "신차"},
        ])

    def test_middle_and_product_options_include_all(self):
        mids, prods = drilldown_options(self.dims, "반도체", "메모리반도체")
        self.assertEqual(mids, [ALL_OPTION, "메모리반도체", "시스템반도체"])
        self.assertEqual(prods, [ALL_OPTION, "DRAM", "NAND"])

    def test_middle_all_limits_product_to_all(self):
        _, prods = drilldown_options(self.dims, "반도체", ALL_OPTION)
        self.assertEqual(prods, [ALL_OPTION])

    def test_selection_uses_correct_mart_level(self):
        self.assertEqual(
            product_monitor_selection("반도체", ALL_OPTION, ALL_OPTION),
            ("mart_export_top20_monthly", "AND item20=?", ("반도체",), "반도체"),
        )
        self.assertEqual(
            product_monitor_selection("반도체", "메모리반도체", ALL_OPTION),
            ("mart_export_middle_monthly", "AND item20=? AND middle_category=?", ("반도체", "메모리반도체"), "메모리반도체"),
        )
        self.assertEqual(
            product_monitor_selection("반도체", "메모리반도체", "DRAM"),
            ("mart_export_product_monthly", "AND item20=? AND middle_category=? AND product=?", ("반도체", "메모리반도체", "DRAM"), "DRAM"),
        )


if __name__ == "__main__":
    unittest.main()
