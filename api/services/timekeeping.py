"""Authoritative application time helpers.

Rent due dates and payment cycles are Kenyan business rules, so they must not
depend on the timezone of a Vercel instance or a tenant's device.
"""
from datetime import datetime, timedelta, timezone

# Kenya observes East Africa Time year-round (UTC+03:00), with no daylight
# saving time. A fixed offset also works in Windows test environments that do
# not ship the optional IANA ``tzdata`` database.
KENYA_TIMEZONE = timezone(timedelta(hours=3), name="Africa/Nairobi")


def kenya_now() -> datetime:
    return datetime.now(KENYA_TIMEZONE)


def kenya_today():
    return kenya_now().date()
