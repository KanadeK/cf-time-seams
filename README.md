# cf-time-seams

Check a collection of local NetCDF time shards before concatenating them. Find
duplicate timestamps, overlapping file ranges, cadence gaps and discontinuous
time bounds with the original file and array index attached to each finding.

[中文说明](README.zh-CN.md) · Python 3.11+ · MIT · v0.1.0

Suppose one export ends on January 2 and the next starts on January 4. Both files
are individually readable. This tool reports the missing daily step before a
combined dataset conceals which source file introduced it.

## Install and try

```sh
git clone https://github.com/KanadeK/cf-time-seams.git
cd cf-time-seams
python -m venv .venv
# POSIX: source .venv/bin/activate
# PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
python examples/make_demo.py .demo
cf-time-seams ".demo/clean/*.nc" --step-seconds 86400 --json
# exit 0; four contiguous points in the 360_day calendar
cf-time-seams ".demo/gap/*.nc" --step-seconds 86400 --json
# exit 1; one cadence_gap, first.nc index 1 -> second.nc index 0
```

Source installation and wheels on GitHub Releases are supported. This project is
not published to PyPI. To uninstall: `python -m pip uninstall cf-time-seams`.
The demo directory and virtual environment can then be deleted. Inputs are never
modified and no persistent cache is created by the tool.

## Declare the intended collection

```sh
cf-time-seams "exports/*.nc" --step-seconds 3600 --tolerance-seconds 0.001
cf-time-seams jan.nc feb.nc mar.nc --monthly --check-bounds
cf-time-seams "exports/*.nc" --time forecast_time --step-seconds 86400 --json
```

- Choose exactly one cadence. Fixed steps are seconds in the declared calendar;
  monthly means the same day and time in consecutive months. It does not clamp
  month ends or infer a frequency. Monthly checks require zero tolerance.
- Files must be continuous, nonoverlapping shards of **one logical series**.
  Do not pass separate variables, ensemble members or spatial tiles that share
  the same time axis. A single point cannot establish cadence; it is accepted.
- Supported calendars: standard/gregorian, proleptic_gregorian, julian,
  noleap/365_day, all_leap/366_day and 360_day. Equivalent aliases normalize;
  different calendars fail instead of being silently converted. Units and epochs
  may differ and are decoded using cftime. Supported years: 1–9999.
- Each input axis must strictly increase. File range overlap is checked using
  the running maximum end, including nested and interleaved ranges. The global
  sorted sequence is checked for duplicate timestamps and declared cadence.
- `--check-bounds` requires time.bounds in every file, shaped `(time, 2)`.
  It checks positive width, timestamp containment, overlap and gaps using an
  interval sweep. Without this flag, bounds are explicitly **not checked**.
- Diagnostics use zero-based time indices. JSON has schema_version, counts,
  findings and findings_omitted. `--max-findings 0` suppresses examples without
  suppressing detection or changing the exit status. Counts describe diagnostic
  events, not distinct missing records or all overlapping file pairs.

Exit status: **0** completed with no findings; **1** completed with findings;
**2** invalid input/options or an incomplete check. On an input error, `--json`
returns an error object; argparse usage errors still go to stderr.

## Python API

```python
from cf_time_seams.core import audit, InputError

report = audit(["first.nc", "second.nc"], step_seconds=86400, max_findings=20)
print(report["ok"], report["counts"])
```

InputError means the collection could not be checked completely. No partial
clean result is returned. A clean report does not verify data values, grid
alignment, expected start/end coverage, or scientific correctness.

## Scope, cost and alternatives

The tool reads the selected root-level time variable and, when requested, its
bounds. It never loads data variables, combines files or repairs them. Time
coordinates are held in memory and sorted: O(N log N) time, O(N) memory; default
cap 1,000,000 points (`--max-points`). Decoding can use hundreds of MB at this cap.
Finding samples default to 100. Files must be stable local snapshots. Native
NetCDF/HDF5 libraries are dependencies, so use OS resource limits for untrusted
files. cftime decoding has microsecond precision; sub-microsecond analysis,
custom calendars, leap-second calendars, climatologies, remote URLs, groups,
multidimensional time and automatic repair are unsupported. No claim of full
CF compliance is made. Tolerance applies to cadence/bound seams, not exact
duplicates, monotonicity, containment or file-range overlap.

[nctime](https://espri-mod.github.io/nctime/) already provides time validation for
ESGF project conventions. Prefer it for that workflow. This CLI accepts arbitrary
filenames without ESGF INI configuration and reports coordinate-level evidence.
[xarray](https://docs.xarray.dev/en/stable/generated/xarray.open_mfdataset.html)
combines datasets; this tool preflights the uncombined inputs. Historical
[overlap reports](https://github.com/pydata/xarray/issues/4077) motivated this
workflow, without implying that current xarray versions retain that bug.
Semantics follow the supported subset of [CF 1.12 time conventions](https://cfconventions.org/Data/cf-conventions/cf-conventions-1.12/cf-conventions.html#time-coordinate).

## Verification and licenses

`python -m unittest discover -s tests -v` creates real NetCDF fixtures, exercises
multiple calendars/epochs, nested ranges, bounds, invalid encodings and CLI exit
codes. CI runs on Linux, macOS and Windows with Python 3.11/3.13. See
[CONTRIBUTING](CONTRIBUTING.md) and [SECURITY](SECURITY.md).

Original code and synthetic examples are MIT. Runtime dependencies are netCDF4
(MIT), cftime (MIT), NumPy (BSD-3-Clause and bundled permissive notices), plus
transitive certifi (MPL-2.0) and packaging (Apache-2.0 OR BSD-2-Clause).
Native wheels contain NetCDF/HDF5 and related libraries with their own notices;
pip retains dependency license files. No dependency source or datasets are copied
into this repository. See [THIRD_PARTY.md](THIRD_PARTY.md).
