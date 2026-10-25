"""Read local time axes and diagnose collection seams without combining data."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import cftime
import netCDF4
import numpy as np

CALENDARS = {
    "standard": "standard",
    "gregorian": "standard",
    "proleptic_gregorian": "proleptic_gregorian",
    "julian": "julian",
    "noleap": "noleap",
    "365_day": "noleap",
    "all_leap": "all_leap",
    "366_day": "all_leap",
    "360_day": "360_day",
}


class InputError(ValueError):
    """The requested check could not be completed."""


def microseconds(value, *, positive=False):
    """Parse seconds exactly, rejecting nonfinite or sub-microsecond values."""
    try:
        number = Decimal(str(value))
        if not number.is_finite() or not 0 <= number <= Decimal("1e12"):
            raise ValueError
        scaled = number * 1_000_000
        if scaled != scaled.to_integral_value() or (positive and scaled == 0):
            raise ValueError
        return int(scaled)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise InputError(
            "seconds must be finite, nonnegative, <=1e12, with microsecond precision"
            + (" and greater than zero" if positive else "")
        ) from exc


def delta_us(later, earlier):
    delta = later - earlier
    return (delta.days * 86400 + delta.seconds) * 1_000_000 + delta.microseconds


def iso(date):
    return date.isoformat()


@dataclass(frozen=True)
class Point:
    date: object
    file: str
    index: int
    lower: object = None
    upper: object = None

    def location(self):
        return {"file": self.file, "index": self.index, "time": iso(self.date)}


class Findings:
    def __init__(self, limit):
        self.counts = Counter()
        self.items = []
        self.limit = limit

    def add(self, code, left, right=None, **details):
        self.counts[code] += 1
        if len(self.items) < self.limit:
            item = {"code": code, "left": left.location(), **details}
            if right is not None:
                item["right"] = right.location()
            self.items.append(item)


def decode(variable, units, calendar, context):
    if np.dtype(variable.dtype).kind not in "iuf":
        raise InputError(f"{context}: time values must be numeric")
    values = variable[:]
    if np.ma.getmaskarray(values).any() or not np.isfinite(values).all():
        raise InputError(f"{context}: masked or nonfinite time values")
    try:
        dates = cftime.num2date(values, units, calendar=calendar, only_use_cftime_datetimes=True)
        dates = np.asarray(dates, dtype=object)
        if any(not 1 <= date.year <= 9999 for date in dates.flat):
            raise InputError(f"{context}: supported years are 1 through 9999")
        return dates
    except (ValueError, OverflowError, TypeError) as exc:
        raise InputError(f"{context}: unsupported time encoding: {exc}") from exc


def read_axis(path, time_name, check_bounds, remaining):
    try:
        with netCDF4.Dataset(str(path), mode="r") as dataset:
            if time_name not in dataset.variables:
                raise InputError(f"{path}: missing root variable {time_name!r}")
            var = dataset.variables[time_name]
            if var.ndim != 1 or var.size == 0:
                raise InputError(f"{path}: expected a nonempty one-dimensional time variable")
            if var.size > remaining:
                raise InputError("max_points exceeded; increase the limit explicitly")
            if any(name in var.ncattrs() for name in ("climatology", "month_lengths")):
                raise InputError(f"{path}: climatology/custom calendars are unsupported")
            raw_calendar = getattr(var, "calendar", "standard")
            if not isinstance(raw_calendar, str) or raw_calendar not in CALENDARS:
                raise InputError(f"{path}: unsupported calendar")
            calendar = CALENDARS[raw_calendar]
            units = getattr(var, "units", None)
            if not isinstance(units, str) or not units:
                raise InputError(f"{path}: missing time units")
            dates = decode(var, units, calendar, str(path))
            bounds = None
            if check_bounds:
                name = getattr(var, "bounds", None)
                if not isinstance(name, str) or name not in dataset.variables:
                    raise InputError(
                        f"{path}: --check-bounds requires a valid time.bounds variable"
                    )
                bound_var = dataset.variables[name]
                if bound_var.shape != (var.size, 2) or bound_var.dimensions[0] != var.dimensions[0]:
                    raise InputError(f"{path}: bounds must have shape (time, 2)")
                bound_calendar = getattr(bound_var, "calendar", raw_calendar)
                if not isinstance(bound_calendar, str) or CALENDARS.get(bound_calendar) != calendar:
                    raise InputError(f"{path}: bounds calendar differs from the time calendar")
                bound_units = getattr(bound_var, "units", units)
                if not isinstance(bound_units, str):
                    raise InputError(f"{path}: invalid bounds units")
                bounds = decode(bound_var, bound_units, calendar, f"{path}:bounds")
            points = [
                Point(
                    date,
                    str(path),
                    i,
                    bounds[i, 0] if bounds is not None else None,
                    bounds[i, 1] if bounds is not None else None,
                )
                for i, date in enumerate(dates)
            ]
            return calendar, points
    except InputError:
        raise
    except (OSError, RuntimeError, ValueError, TypeError, OverflowError) as exc:
        raise InputError(f"{path}: cannot read time axis: {exc}") from exc


def audit(
    paths,
    *,
    step_seconds=None,
    monthly=False,
    tolerance_seconds=0,
    time_name="time",
    check_bounds=False,
    max_points=1_000_000,
    max_findings=100,
):
    """Audit continuous, nonoverlapping shards; return a JSON-serializable report.

    Exactly one cadence is required. Monthly means same day and time in consecutive
    calendar months, not month-end clamping. Indices in reports are zero-based.
    """
    if (step_seconds is None) == (not monthly):
        raise InputError("choose exactly one of step_seconds or monthly")
    if (
        not isinstance(max_points, int)
        or max_points < 1
        or not isinstance(max_findings, int)
        or max_findings < 0
    ):
        raise InputError("max_points must be positive and max_findings nonnegative")
    tolerance = microseconds(tolerance_seconds)
    step = microseconds(step_seconds, positive=True) if step_seconds is not None else None
    if step is not None and tolerance * 2 >= step:
        raise InputError("tolerance must be smaller than half the expected step")
    if monthly and tolerance:
        raise InputError("monthly cadence requires zero tolerance")
    paths = [Path(path).resolve() for path in paths]
    if not paths or len(set(paths)) != len(paths):
        raise InputError("provide at least one file; duplicate resolved paths are not allowed")
    if any(not path.is_file() for path in paths):
        raise InputError("every input must be a local regular file")
    findings = Findings(max_findings)
    axes = []
    points = []
    expected_calendar = None
    for path in paths:
        calendar, axis = read_axis(path, time_name, check_bounds, max_points - len(points))
        if expected_calendar is not None and calendar != expected_calendar:
            raise InputError("mixed calendars cannot be compared; separate the collections")
        expected_calendar = calendar
        for left, right in zip(axis, axis[1:], strict=False):
            if right.date <= left.date:
                findings.add("axis_not_increasing", left, right)
        axes.append(axis)
        points.extend(axis)
    # Ranges are checked with a running frontier, so nested files cannot hide overlap.
    ranges = sorted(
        ((min(axis, key=lambda p: p.date), max(axis, key=lambda p: p.date)) for axis in axes),
        key=lambda pair: (pair[0].date, pair[0].file),
    )
    frontier = ranges[0][1]
    for start, end in ranges[1:]:
        if start.date <= frontier.date:
            findings.add("file_range_overlap", frontier, start)
        if end.date > frontier.date:
            frontier = end
    ordered = sorted(points, key=lambda p: (p.date, p.file, p.index))
    for left, right in zip(ordered, ordered[1:], strict=False):
        difference = delta_us(right.date, left.date)
        if difference == 0:
            findings.add("duplicate_time", left, right)
        elif monthly:
            a, b = left.date, right.date
            months = (b.year - a.year) * 12 + b.month - a.month
            if months != 1 or (a.day, a.hour, a.minute, a.second, a.microsecond) != (
                b.day,
                b.hour,
                b.minute,
                b.second,
                b.microsecond,
            ):
                findings.add("monthly_cadence", left, right)
        elif abs(difference - step) > tolerance:
            findings.add(
                "cadence_gap" if difference > step else "cadence_short",
                left,
                right,
                delta_seconds=difference / 1_000_000,
                expected_seconds=step / 1_000_000,
            )
    if check_bounds:
        valid_intervals = []
        for point in ordered:
            if point.lower >= point.upper:
                findings.add(
                    "invalid_bounds", point, lower=iso(point.lower), upper=iso(point.upper)
                )
            else:
                if not point.lower <= point.date <= point.upper:
                    findings.add("time_outside_bounds", point)
                valid_intervals.append(point)
        intervals = sorted(valid_intervals, key=lambda p: (p.lower, p.upper, p.file, p.index))
        if intervals:
            frontier = intervals[0]
            for point in intervals[1:]:
                difference = delta_us(point.lower, frontier.upper)
                if abs(difference) > tolerance:
                    findings.add(
                        "bounds_gap" if difference > 0 else "bounds_overlap",
                        frontier,
                        point,
                        delta_seconds=difference / 1_000_000,
                    )
                if point.upper > frontier.upper:
                    frontier = point
    total = sum(findings.counts.values())
    return {
        "schema_version": 1,
        "ok": total == 0,
        "calendar": expected_calendar,
        "files": len(paths),
        "points": len(points),
        "time_variable": time_name,
        "cadence": {
            "monthly": monthly,
            "step_seconds": step / 1_000_000 if step else None,
            "tolerance_seconds": tolerance / 1_000_000,
        },
        "bounds_checked": check_bounds,
        "first": iso(ordered[0].date),
        "last": iso(ordered[-1].date),
        "finding_count": total,
        "counts": dict(sorted(findings.counts.items())),
        "findings": findings.items,
        "findings_omitted": total - len(findings.items),
    }
