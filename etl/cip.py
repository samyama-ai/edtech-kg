"""The CIP key — one canonical form, and what is not a programme.

Split out of `etl/load_education.py` at the 500-line review limit, and split
by SUBJECT: that module decides what a load writes, this one decides what a
programme is CALLED. `etl/load_cipsoc.py` needs the second without the first,
and importing a loader to borrow a key is the wrong way round.

Two defects made this its own module, both merged in #187:

  * `cipcode_6digit` arrives as an INT, so `str()` dropped the leading zero
    from every code below `10.0000`. 70 of 664 `Programme` nodes carried a
    short key, and the CIP-SOC crosswalk keys on the dotted six-digit form —
    so the join failed QUIETLY, dropping about a tenth of programmes.
  * IPEDS files an institution-level TOTAL under CIP 99, written as a
    `Programme` like any other. Measured on Virginia 2022: 141,688 awards
    under it against 141,908 under every real code combined, because the
    first is the sum of the second.
"""

from __future__ import annotations

import re

from etl.engine import Refused

#: A normalised CIP whose SERIES — its first two digits — is `00` is not a
#: programme. `99` normalises to `000099`, and IPEDS's own series run 01-61,
#: so nothing real lands here. Measured on Virginia 2022: series `00` covers
#: exactly the 13,950 grand-total rows and nothing else. Keyed on the series
#: rather than on the literal `99`, so a 2- or 4-digit subtotal in a future
#: slice is caught by the same rule.
NOT_A_PROGRAMME_SERIES = "00"

#: The two shapes a CIP code is published in: `51.3801` and `513801`.
#: `[0-9]` rather than `\\d`, which also matches non-ASCII numerals — a
#: Unicode digit string would pass `fullmatch` and be zero-padded into
#: something that looks like a CIP. This module's own argument is that a
#: wrong key which parses is worse than one that refuses.
DOTTED = re.compile(r"[0-9]{2}\.[0-9]{4}")
PLAIN = re.compile(r"[0-9]{1,6}")


def cip_code(raw) -> str:
    """The CIP key, in ONE canonical form: six digits, zero-padded.

    **The API returns `cipcode_6digit` as an int**, so `str()` dropped the
    leading zero from every code below `10.0000` — `01.0000` arrived as
    `"10000"`. 70 of 664 `Programme` nodes carried a short key.

    That is not cosmetic. `docs/sources/cip-soc-crosswalk.md` keys on the
    dotted form (`01.0000`), so a join against a stripped code fails, and
    fails QUIETLY — the query returns rows, just fewer. Every programme whose
    CIP begins with zero drops out, about a tenth of them.

    Digits-only rather than dotted, because 594 of the 664 already-loaded
    nodes are digits-only and the crosswalk reader can drop a dot far more
    safely than this can invent one — it accepts both, so the join normalises
    on the way in rather than needing a second form stored here.
    """
    text = str(raw).strip()
    # **Shape-checked, not just digit-checked.** `str(10000.0)` is
    # `"10000.0"`, and stripping the dot from that gave `"100000"` — a valid-
    # looking six-digit code that is silently the WRONG programme. A wrong key
    # that parses is worse than one that refuses, and this whole issue exists
    # because of a key that looked fine.
    if DOTTED.fullmatch(text):
        return text.replace(".", "")
    if PLAIN.fullmatch(text):
        return text.zfill(6)
    raise Refused(0, f"not a CIP code: {raw!r}")
