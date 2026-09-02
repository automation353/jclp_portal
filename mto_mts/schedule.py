"""Monthly-cycle helpers (Change instruction 14).

Rule from the 11-Aug meeting:
    Operations uploads on the 1st (2nd at latest).
    Sales reviews from the 2nd to the 5th.
    The file locks automatically on the 5th at midnight — i.e. at
    00:00 on the 6th, in the same month the file was uploaded.

If the upload happens on or after the 6th (i.e. the review window for
this calendar month is already gone), the lock is deferred to the 6th
of the NEXT calendar month.
"""

import datetime as dt


def compute_lock_at(uploaded_at):
    """Return the timezone-aware UTC datetime at which this upload should
    auto-lock, per the review-cycle rule above.

    Example:
        upload on 2026-08-01 07:00 UTC → 2026-08-06 00:00:00 UTC
        upload on 2026-08-10 07:00 UTC → 2026-09-06 00:00:00 UTC
    """
    if uploaded_at.day <= 5:
        year, month = uploaded_at.year, uploaded_at.month
    else:
        # roll to the next month
        month = uploaded_at.month + 1
        year = uploaded_at.year
        if month > 12:
            month = 1
            year += 1

    return dt.datetime(year, month, 6, 0, 0, 0, tzinfo=dt.timezone.utc)
