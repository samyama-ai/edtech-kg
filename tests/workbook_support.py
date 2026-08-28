"""Building a minimal but valid `.xlsx`, for every test that needs one.

Its own module because four test files need it and a test module importing
another test module is how a fixture ends up owned by whichever file happened
to define it first — `test_probe_sced.py` imported it from
`test_probe_cipsoc.py`, so the SCED tests depended on the CIP-SOC tests
existing under that name.

The same reason the probes share `probe_cipsoc.rows` rather than each carrying
a reader: one builder, so two suites cannot come to disagree about what a
workbook looks like while both pass.
"""

from __future__ import annotations

import zipfile
from xml.sax.saxutils import escape, quoteattr


def workbook(path, sheets: dict[str, list[list[str]]], shared: bool = True):
    """Write the SUBSET OF AN .XLSX THIS REPO'S READERS PARSE.

    Not a valid workbook: there is no `[Content_Types].xml`, so Excel would
    refuse it. The readers here go at the zip members directly, and adding the
    part would make the docstring's old claim of "minimal but valid" true
    without making a single test stronger — so the claim is corrected instead.
    What this DOES reproduce is the two shapes those readers must handle.

    `shared=True` puts cell text in the shared-string table, which is what
    Excel does; `False` uses inline strings, which some exporters emit.
    """
    strings: list[str] = []
    seen: dict[str, int] = {}

    def column(index: int) -> str:
        """`A`, `Z`, `AA`… — `chr(65 + col)` produced `[` at column 26.

        A fixture wide enough to reach it built a workbook with cell
        references no reader can place, and the probes place cells BY
        reference — so the test would be exercising a file Excel could not
        have written.
        """
        ref = ""
        while True:
            index, remainder = divmod(index, 26)
            ref = chr(65 + remainder) + ref
            if not index:
                return ref
            index -= 1

    def cell(value, col, row):
        ref = f"{column(col)}{row}"
        if shared:
            # A dict, not `list.index`. Building a wide fixture was quadratic
            # in the number of distinct strings.
            if value not in seen:
                seen[value] = len(strings)
                strings.append(value)
            return f'<c r="{ref}" t="s"><v>{seen[value]}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(value)}</t></is></c>'

    parts, rels, entries = [], [], []
    for i, (name, table) in enumerate(sheets.items(), start=1):
        # Empty cells are OMITTED, which is what Excel does — it does not write
        # a blank `<c>`. That is why every cell carries its `r` reference and
        # why the probe must place values by reference rather than by order.
        body = "".join(
            f'<row r="{r}">'
            + "".join(cell(v, c, r) for c, v in enumerate(row) if v != "")
            + "</row>"
            for r, row in enumerate(table, start=1)
        )
        entries.append((f"xl/worksheets/sheet{i}.xml",
                        '<?xml version="1.0"?><worksheet xmlns="http://schemas.openxmlformats.org/'
                        f'spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>'))
        # ESCAPED. A sheet name or a cell value carrying `&` or `<` — both
        # legal in a real workbook — produced XML the reader could not parse,
        # so a fixture testing an awkward value failed on the fixture.
        parts.append(f'<sheet name={quoteattr(name)} sheetId="{i}" r:id="rId{i}"/>')
        rels.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/'
                    f'officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')

    with zipfile.ZipFile(path, "w") as z:
        z.writestr("xl/workbook.xml",
                   '<?xml version="1.0"?><workbook xmlns="http://schemas.openxmlformats.org/'
                   'spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/'
                   f'officeDocument/2006/relationships"><sheets>{"".join(parts)}</sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels",
                   '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/'
                   f'package/2006/relationships">{"".join(rels)}</Relationships>')
        if shared:
            si = "".join(f"<si><t>{escape(s)}</t></si>" for s in strings)
            z.writestr("xl/sharedStrings.xml",
                       '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
                       f'spreadsheetml/2006/main">{si}</sst>')
        for name, content in entries:
            z.writestr(name, content)
    return path
