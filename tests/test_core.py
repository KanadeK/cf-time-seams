import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import netCDF4

from cf_time_seams.cli import main
from cf_time_seams.core import InputError, audit


class AxisTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def nc(self, name, times, calendar="standard", units="days since 2000-01-01", bounds=None):
        path = self.root / name
        with netCDF4.Dataset(path, "w") as ds:
            ds.createDimension("time", len(times))
            var = ds.createVariable("time", "f8", ("time",))
            var.units = units
            var.calendar = calendar
            var[:] = times
            if bounds is not None:
                ds.createDimension("nv", 2)
                bvar = ds.createVariable("time_bounds", "f8", ("time", "nv"))
                var.bounds = "time_bounds"
                bvar[:] = bounds
        return path

    def check(self, paths, **kwargs):
        return audit(paths, step_seconds=86400, **kwargs)

    def test_different_epochs_and_units(self):
        a = self.nc("a.nc", [0, 1])
        b = self.nc("b.nc", [0, 24], units="hours since 2000-01-03")
        result = self.check([b, a])
        self.assertTrue(result["ok"])
        self.assertEqual(result["points"], 4)
        self.assertEqual(result["last"], "2000-01-04T00:00:00")

    def test_gap_between_files_has_original_locations(self):
        a = self.nc("a.nc", [0, 1])
        b = self.nc("b.nc", [3, 4])
        result = self.check([a, b])
        self.assertEqual(result["counts"], {"cadence_gap": 1})
        self.assertEqual(result["findings"][0]["left"]["index"], 1)
        location = Path(result["findings"][0]["right"]["file"])
        self.assertTrue(location.is_absolute())
        self.assertTrue(location.samefile(b))

    def test_duplicate_inside_axis(self):
        result = self.check([self.nc("a.nc", [0, 1, 1, 2])])
        self.assertEqual(result["counts"], {"axis_not_increasing": 1, "duplicate_time": 1})

    def test_duplicate_across_files(self):
        result = self.check([self.nc("a.nc", [0, 1]), self.nc("b.nc", [1, 2])])
        self.assertEqual(result["counts"], {"duplicate_time": 1, "file_range_overlap": 1})

    def test_interleaved_ranges_without_equal_points(self):
        result = self.check([self.nc("a.nc", [0, 2]), self.nc("b.nc", [1, 3])])
        self.assertEqual(result["counts"], {"file_range_overlap": 1})

    def test_nested_ranges_keep_frontier(self):
        result = self.check(
            [self.nc("a.nc", [0, 10]), self.nc("b.nc", [2, 3]), self.nc("c.nc", [5, 6])]
        )
        self.assertEqual(result["counts"]["file_range_overlap"], 2)

    def test_descending_axis_fails_despite_sorted_collection(self):
        result = self.check([self.nc("a.nc", [2, 1, 0])])
        self.assertEqual(result["counts"], {"axis_not_increasing": 2})

    def test_360_day_february_30(self):
        result = self.check([self.nc("a.nc", [58, 59, 60], calendar="360_day")])
        self.assertTrue(result["ok"])
        self.assertEqual(result["first"], "2000-02-29T00:00:00")
        self.assertEqual(result["last"], "2000-03-01T00:00:00")

    def test_noleap_does_not_expect_february_29(self):
        result = self.check([self.nc("a.nc", [58, 59], calendar="noleap")])
        self.assertTrue(result["ok"])
        self.assertEqual(result["last"], "2000-03-01T00:00:00")

    def test_calendar_aliases_match(self):
        result = self.check(
            [self.nc("a.nc", [0], calendar="365_day"), self.nc("b.nc", [1], calendar="noleap")]
        )
        self.assertTrue(result["ok"])

    def test_mixed_calendars_rejected(self):
        with self.assertRaisesRegex(InputError, "mixed calendars"):
            self.check([self.nc("a.nc", [0]), self.nc("b.nc", [1], calendar="noleap")])

    def test_monthly_leap_year_variable_durations(self):
        result = audit([self.nc("a.nc", [0, 31, 60, 91])], monthly=True)
        self.assertTrue(result["ok"])

    def test_monthly_missing_month(self):
        result = audit([self.nc("a.nc", [0, 60])], monthly=True)
        self.assertEqual(result["counts"], {"monthly_cadence": 1})

    def test_monthly_drift_fails(self):
        result = audit([self.nc("a.nc", [0, 32])], monthly=True)
        self.assertFalse(result["ok"])

    def test_fixed_step_tolerance(self):
        path = self.nc("a.nc", [0, 86400.001], units="seconds since 2000-01-01")
        self.assertTrue(self.check([path], tolerance_seconds="0.002")["ok"])
        self.assertFalse(self.check([path])["ok"])

    def test_short_cadence(self):
        result = self.check([self.nc("a.nc", [0, 0.5])])
        self.assertEqual(result["counts"], {"cadence_short": 1})

    def test_contiguous_bounds(self):
        result = self.check(
            [
                self.nc("a.nc", [0.5, 1.5], bounds=[[0, 1], [1, 2]]),
                self.nc("b.nc", [2.5], bounds=[[2, 3]]),
            ],
            check_bounds=True,
        )
        self.assertTrue(result["ok"])

    def test_bounds_gap_can_exist_with_regular_points(self):
        result = self.check(
            [self.nc("a.nc", [0.5, 1.5], bounds=[[0, 0.9], [1, 2]])], check_bounds=True
        )
        self.assertEqual(result["counts"], {"bounds_gap": 1})

    def test_nested_bounds_overlap_not_false_gap(self):
        result = self.check(
            [self.nc("a.nc", [0.5, 1.5, 2.5], bounds=[[0, 4], [1, 2], [2, 3]])], check_bounds=True
        )
        self.assertEqual(result["counts"], {"bounds_overlap": 2})

    def test_invalid_bounds_and_outside_time(self):
        result = self.check(
            [self.nc("a.nc", [0.5, 1.5], bounds=[[2, 1], [2, 3]])], check_bounds=True
        )
        self.assertEqual(result["counts"], {"invalid_bounds": 1, "time_outside_bounds": 1})

    def test_bounds_required_when_requested(self):
        with self.assertRaisesRegex(InputError, "requires"):
            self.check([self.nc("a.nc", [0])], check_bounds=True)

    def test_nonfinite_values_fail_closed(self):
        for value in [float("nan"), float("inf"), -float("inf")]:
            with self.subTest(value=value), self.assertRaises(InputError):
                self.check([self.nc("a.nc", [0, value])])

    def test_masked_values_fail_closed(self):
        path = self.nc("a.nc", [0, netCDF4.default_fillvals["f8"]])
        with self.assertRaisesRegex(InputError, "masked"):
            self.check([path])

    def test_missing_and_unsupported_metadata(self):
        path = self.nc("a.nc", [0])
        with netCDF4.Dataset(path, "a") as ds:
            ds.variables["time"].delncattr("units")
        with self.assertRaisesRegex(InputError, "units"):
            self.check([path])
        for calendar in ["none", "utc", "unknown"]:
            with self.subTest(calendar=calendar), self.assertRaises(InputError):
                self.check([self.nc("a.nc", [0], calendar=calendar)])

    def test_climatology_rejected(self):
        path = self.nc("a.nc", [0])
        with netCDF4.Dataset(path, "a") as ds:
            ds.variables["time"].climatology = "clim"
        with self.assertRaisesRegex(InputError, "climatology"):
            self.check([path])

    def test_empty_axis_and_point_limit(self):
        with self.assertRaises(InputError):
            self.check([self.nc("a.nc", [])])
        with self.assertRaisesRegex(InputError, "max_points"):
            self.check([self.nc("a.nc", [0, 1])], max_points=1)

    def test_duplicate_paths_rejected(self):
        path = self.nc("a.nc", [0])
        with self.assertRaises(InputError):
            self.check([path, path])

    def test_bad_file_not_clean(self):
        path = self.root / "bad.nc"
        path.write_text("not netcdf")
        with self.assertRaises(InputError):
            self.check([path])

    def test_bad_parameters(self):
        path = self.nc("a.nc", [0, 1])
        for value in [0, -1, "NaN", "Infinity", "1e9999", "0.0000001"]:
            with self.subTest(value=value), self.assertRaises(InputError):
                audit([path], step_seconds=value)
        with self.assertRaises(InputError):
            audit([path], monthly=True, step_seconds=1)
        with self.assertRaises(InputError):
            audit([path])
        with self.assertRaises(InputError):
            audit([path], step_seconds=1, tolerance_seconds="0.5")

    def test_findings_cap_does_not_change_result(self):
        result = self.check([self.nc("a.nc", [0, 2, 4, 6])], max_findings=0)
        self.assertFalse(result["ok"])
        self.assertEqual(result["finding_count"], 3)
        self.assertEqual(result["findings_omitted"], 3)

    def test_cli_json_glob_and_exit_codes(self):
        self.nc("a.nc", [0, 1])
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main([str(self.root / "*.nc"), "--step-seconds", "86400", "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(out.getvalue())["ok"])
        self.nc("b.nc", [3])
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "cf_time_seams",
                str(self.root / "*.nc"),
                "--step-seconds",
                "86400",
                "--json",
            ],
            capture_output=True,
            text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)["counts"], {"cadence_gap": 1})
        with contextlib.redirect_stdout(io.StringIO()) as out:
            code = main([str(self.root / "missing*.nc"), "--monthly", "--json"])
        self.assertEqual(code, 2)
        self.assertIn("error", json.loads(out.getvalue()))

    def test_readonly_input(self):
        path = self.nc("a.nc", [0, 1])
        before = path.read_bytes()
        self.assertTrue(self.check([path])["ok"])
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
