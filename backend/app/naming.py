"""Construction and validation of stored object names.

The name a client supplies to GET /weather-file-content/{file} is passed to a
bucket, which makes it a path-traversal surface. Every name is matched against
OBJECT_NAME_PATTERN *before* any storage call, so only names of our own shape
ever reach GCS.
"""

import re
from datetime import date, datetime, timezone

# weather_<lat>_<lon>_<start>_<end>_<timestamp>.json
# Coordinates are always signed-optional with exactly 4 decimal places, which
# is what build_object_name emits.
# re.ASCII ensures \d matches only ASCII 0-9, not Unicode digits like ١٩ or １９.
# This is critical because build_object_name only generates ASCII output, so
# accepting Unicode digits would violate the security promise: "only names this
# service could itself have generated."
OBJECT_NAME_PATTERN = re.compile(
    r"^weather_"
    r"(-?\d{1,3}\.\d{4})_"          # latitude
    r"(-?\d{1,3}\.\d{4})_"          # longitude
    r"(\d{4}-\d{2}-\d{2})_"         # start date
    r"(\d{4}-\d{2}-\d{2})_"         # end date
    r"(\d{8}T\d{6}Z)"               # UTC timestamp
    r"\.json$",
    re.ASCII,
)

TIMESTAMP_FORMAT = "%Y%m%dT%H%M%SZ"


def build_object_name(
    latitude: float,
    longitude: float,
    start: date,
    end: date,
    now: datetime | None = None,
) -> str:
    """Return the object name for one stored fetch.

    `now` is injectable so tests can assert an exact string.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime(TIMESTAMP_FORMAT)
    return (
        f"weather_{latitude:.4f}_{longitude:.4f}"
        f"_{start.isoformat()}_{end.isoformat()}_{stamp}.json"
    )


def is_valid_object_name(name: str) -> bool:
    """True only for names this service could itself have generated."""
    return bool(OBJECT_NAME_PATTERN.fullmatch(name))
