"""The two field names, in one place.

`etl/course_reader.py` finds the regions and `etl/course_page.py` decides what
they mean, so the prefix they both key on cannot live in either without one
importing the other for a string.
"""

#: **TWO different prerequisite fields**, and the difference between them is
#: the whole question.
#:
#: `field-prerequisite-courses` is an ENTITY REFERENCE — the CMS links it to
#: other course pages, and `etl/probe_pwcs.py` reads exactly this. `field-pr`
#: is a free-text paragraph. A district can state its prerequisites completely
#: and usefully in the second and still publish no edge anybody can traverse.
#:
#: The first version matched `field--name-field-pr\b`, whose word boundary
#: excludes `field-prerequisite-courses` — so it read the free-text field on
#: every district and reported PWCS at 0% linked. The control is the only
#: reason that was caught.
FIELD_OPENS = "field--name-field-"


