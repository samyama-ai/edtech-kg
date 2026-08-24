"""Synthetic catalogue markup, shared by the pwcs test modules.

The real pages are large and cached; these builders render the few elements the
parser actually keys on, so a test can construct a page the district does not
publish — an odd depth, a row naming a subject, a section with no rows.

Shared rather than duplicated because a builder that drifts between two test
files makes both of them pass while describing different pages.
"""

from __future__ import annotations


def row(path: str, credits: str = "1") -> str:
    return (f'<article about="{path}" class="node row degree-row">'
            f'<div class="col-10"><a href="{path}">A course</a></div>'
            f'<span class="field field--name-field-credits field__item">{credits}</span>'
            f'</article>')


def section(title: str, *paths: str, credits: str = "1") -> str:
    return (f'<h2 class="field field--name-field-degree-section-title '
            f'field__item">{title}</h2>'
            f'<div class="field field--name-field-degree-section-courses">'
            + "".join(row(p, credits) for p in paths) + "</div>")


def titled(name: str) -> str:
    return f"<html><h1>{name}</h1></html>"


# The sitemap these fixtures resolve against. One definition: a second copy in
# a test file is the drift this module exists to prevent, and two builders
# disagreeing about what is published makes both files pass while describing
# different catalogues.
PUBLISHED = {"/a/one", "/a/two", "/b/three"}
