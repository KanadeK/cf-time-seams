# Third-party dependencies

This repository includes no copied third-party implementation or research datasets.
The demo generator and test fixtures were written for this project.

| Runtime distribution | License | Upstream |
|---|---|---|
| netCDF4 | MIT | https://github.com/Unidata/netcdf4-python |
| cftime | MIT | https://github.com/Unidata/cftime |
| numpy | BSD-3-Clause and bundled permissive notices (0BSD, MIT, Zlib, CC0-1.0 in tested wheel) | https://github.com/numpy/numpy |
| certifi (transitive) | MPL-2.0 | https://github.com/certifi/python-certifi |
| packaging (transitive) | Apache-2.0 OR BSD-2-Clause | https://github.com/pypa/packaging |

Python dependencies are installed separately. Their license files remain in their
distributions. netCDF4 wheels bundle native libraries; inspect that wheel's notices
when redistributing an environment. The project wheel contains only this project's
Python code and MIT license. MIT project code can depend on these distributions
without relicensing their upstream files.
