import unittest

import pandas as pd

from Src.module_overlap import build_controlled_configurations, calculate_overlap_metrics, parse_modules


class ModuleOverlapTest(unittest.TestCase):
    def setUp(self):
        self.source = pd.DataFrame(
            {
                "machine": ["M1", "M1", "M1", "M2", "M2"],
                "configuration": ["a", "b", "c", "d", "e"],
                "auxiliary_modules": ["1;2;3;4", "5;6", "7;8;9", "10;11", "12;13;14"],
            }
        )

    def test_module_counts_are_preserved(self):
        expected = [len(parse_modules(value)) for value in self.source["auxiliary_modules"]]
        for level in [0, 0.25, 0.5, 0.75, 1]:
            result = build_controlled_configurations(self.source, level)
            actual = [len(parse_modules(value)) for value in result["auxiliary_modules"]]
            self.assertEqual(expected, actual)

    def test_overlap_is_monotonic_and_reaches_endpoints(self):
        values = [
            calculate_overlap_metrics(build_controlled_configurations(self.source, level))[
                "mean_overlap_coefficient"
            ]
            for level in [0, 0.25, 0.5, 0.75, 1]
        ]
        self.assertEqual(values[0], 0)
        self.assertEqual(values[-1], 1)
        self.assertEqual(values, sorted(values))


if __name__ == "__main__":
    unittest.main()
