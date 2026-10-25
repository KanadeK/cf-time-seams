"""Create small synthetic NetCDF shards. Refuses to overwrite an existing directory."""

import sys
from pathlib import Path

import netCDF4

root = Path(sys.argv[1] if len(sys.argv) > 1 else ".demo")
root.mkdir(parents=True, exist_ok=False)
for folder, data in [("clean", ([0, 1], [2, 3])), ("gap", ([0, 1], [3, 4]))]:
    (root / folder).mkdir()
    for name, times in zip(("first.nc", "second.nc"), data, strict=True):
        with netCDF4.Dataset(root / folder / name, "w") as ds:
            ds.createDimension("time", len(times))
            var = ds.createVariable("time", "f8", ("time",))
            var.units = "days since 2000-01-01"
            var.calendar = "360_day"
            var[:] = times
print(f"Synthetic fixtures created in {root}")
