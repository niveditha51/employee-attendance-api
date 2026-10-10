# REVIEW.md

| # | Where | What is wrong | How you'd notice it | How I fixed it |
|---|---|---|---|---|
| 1 | compute_late_minutes | Puts the IST shift time onto a UTC datetime, so the difference is off by 5h30m | EMP0003 punching in at 04:35Z with a 09:30 shift returns 0, not 35 | Convert the punch to IST first, then compare |
| 2 | compute_late_minutes | Grace is checked in whole minutes, so 09:40:01 gives 0; overnight shifts after midnight are not handled | 09:40:01 should give 10; a 00:30 punch on a 22:00 shift | Compare in seconds (more than 600), move the shift start back a day for overnight shifts |
| 3 | compute_work_hours | Python round() uses banker's rounding on the binary float | 450 seconds (0.125 h) gives 0.12, but half-up gives 0.13 | Use Decimal with ROUND_HALF_UP on whole seconds |
| 4 | compute_overtime | Builds the end on the attendance date, so overnight shifts are wrong; no 30-minute minimum; naive datetimes mix with an aware one | EMP0005 (22:00 to 06:00) returns a huge negative value clamped to 0 instead of 40; 5 minutes returns 5 | Add a day when shift_end <= shift_start, return 0 below 30 minutes, make datetimes aware |
| 5 | MongoClient setup | Not tz_aware, so PyMongo returns naive datetimes | Naive and aware values cannot be subtracted | tz_aware=True plus an _aware helper |
| 6 | create_employee | No validation, check-then-insert race, naive local created_at, raw datetime in the response | Two simultaneous posts both succeed; created_at is not epoch ms | Pydantic validation, unique index with DuplicateKeyError, UTC created_at converted to epoch ms |
| 7 | list_employees | skip is page * page_size so page 1 skips the first page; total ignores the filter; no sort or size limit | page=1 misses the first rows; total is wrong with a department filter | (page - 1) * page_size, count with the same filter, sort by emp_code, limit page_size |
| 8 | punch_in | 500 on unknown employee, status not validated, date taken from server time, race, id and raw datetimes returned, strict punched_at not enforced, late helper called without shift_end | Unknown emp_code crashes; status ABSENT is accepted | 404, Literal status, IST attendance date per overnight rule, unique index, epoch-ms response without id, StrictInt range |
| 9 | list_attendance | Loads all rows and sorts in Python, total computed in Python, no date validation, no tie-breaker sort | Slow and memory-heavy on large data; bad date gives wrong results | Sort, skip and limit in MongoDB, count_documents, validate dates, sort by date then emp_code |

## Looked at and not a defect
- `IST = timezone(timedelta(hours=5, minutes=30))` is correct, because India has no daylight saving.
- The /health endpoint returns ok; I only added a database ping.