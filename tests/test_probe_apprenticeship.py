"""The apprenticeship probe, and the two documents that quote it.

The failure to guard against is not a crash. It is a probe that reports a clean
overlap because it compared nothing — `0 reachable only by apprenticeship`
reads as "the programme route covers everything" and is also what an empty set
gives you. Several of these drive the case where the answer would be wrong
rather than absent.

Workbooks are built in the test, so no network and no committed sample file.
"""

from __future__ import annotations

import io
import subprocess

import pytest

from etl import probe_apprenticeship as probe
from tests.test_probe_cipsoc import workbook as cipsoc_workbook


SHEET = "O-NET-SOC 2019 Crosswalks"


def workbook(rows: list[list[str]]) -> bytes:
    """A single-sheet .xlsx carrying these rows, as bytes.

    Built by `tests.test_probe_cipsoc.workbook` rather than by a second builder
    here — the same reason the probe imports that module's reader instead of
    carrying its own. It OMITS a cell whose value is `""`, which is what Excel
    does for a blank, so a fixture can reach the reader's placement rule.
    """
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, {SHEET: rows})
    return buffer.getvalue()


def crosswalks(monkeypatch, rapids: list[list[str]], cip: list[list[str]]):
    """Serve both O*NET workbooks without touching the network or `data/`."""
    books = {probe.RAPIDS_URL: workbook(rapids), probe.CIP_URL: workbook(cip)}

    def served(url, into):
        # Named, not `books[url]`. A URL the fixture does not fake raised
        # `KeyError: 'https://...'` from inside a lambda, which reads as a
        # broken probe rather than as a test that stopped covering a fetch the
        # probe has started making.
        if url not in books:
            raise AssertionError(
                f"the probe fetched {url}, which this fixture does not serve. "
                f"Add it to `crosswalks()` — a new fetch is exactly what these "
                f"tests must not silently miss.")
        return books[url]

    monkeypatch.setattr(probe, "download", served)


HEADER = ["RAPIDS Code", "RAPIDS Title", "O*NET-SOC 2019 Code", "O*NET-SOC 2019 Title"]


def test_the_suffix_means_a_naive_join_finds_nothing(monkeypatch):
    """The finding this page shares with `code-sets.md`, confirmed on a second
    file rather than cited from the first.

    Every O*NET-SOC code carries a `.NN` suffix, so string equality against a
    SOC code matches nothing — the SAFE failure, because a partial match would
    be a figure nobody could reproduce. Driven with a fixture whose SOC side
    deliberately matches our crosswalk, so a zero means the suffix and not an
    empty comparison.
    """
    crosswalks(monkeypatch,
               [HEADER, ["0001", "Electrician", "47-2111.00", "Electricians"]],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})

    got = probe.routes()
    assert got["apprentice_soc"] == 1, "the rollup lost the occupation"
    assert got["apprenticeable_in_ours"] == 1, (
        "the rolled-up code did not join — the comparison is empty, so the "
        "zero below would mean nothing")
    assert got["naive_string_matches"] == 0, (
        "an O*NET-SOC code matched a SOC code by string equality — the suffix "
        "rule both this page and code-sets.md rest on no longer holds")


def test_an_occupation_reachable_only_by_apprenticeship_is_reported(monkeypatch):
    """The number the whole probe exists for. It has to be a set difference and
    not a count of rows: an occupation reachable by both routes is not part of
    the gap, however many apprenticeship codes point at it."""
    crosswalks(
        monkeypatch,
        [HEADER,
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         # A second apprenticeship code for the SAME occupation. It must not
         # make the occupation count twice.
         ["0002", "Electrician (Maint)", "47-2111.01", "Electricians"],
         ["0003", "Machine Setter", "51-4081.00", "Machine Tool Setters"]],
        [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111", "51-4081"})

    got = probe.routes()
    assert got["rapids_codes"] == 3
    assert got["apprentice_soc"] == 2, "two distinct occupations, not three rows"
    assert got["both_ways"] == 1
    assert got["apprenticeship_only"] == ["51-4081"], (
        "the occupation with no programme route was not reported as the gap")


def test_an_occupation_missing_from_our_crosswalk_is_named_not_counted(monkeypatch):
    """A count of misses is not actionable; the codes are. This is the list a
    reader checks before believing the join is clean."""
    crosswalks(monkeypatch,
               [HEADER, ["0001", "Something New", "99-1234.00", "Novel Job"]],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})

    got = probe.routes()
    assert got["apprentice_soc_missing_from_ours"] == ["99-1234"]


def test_a_crosswalk_with_no_header_is_refused(monkeypatch):
    """O*NET puts two title rows above the header, so it is found by content
    rather than by row number. A file without one is a layout change, not an
    empty answer — and an empty answer here reads as "nothing is
    apprenticeable"."""
    crosswalks(monkeypatch,
               [["some", "other", "columns"], ["0001", "x", "47-2111.00", "y"]],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    with pytest.raises(probe.MalformedSource, match="no header row"):
        probe.routes()


def test_a_crosswalk_that_parses_to_nothing_is_refused(monkeypatch):
    """Zero rows is the reading that would report a perfect overlap."""
    crosswalks(monkeypatch,
               [HEADER],
               [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    with pytest.raises(probe.MalformedSource, match="parsed to zero rows"):
        probe.routes()


def test_a_second_sheet_is_refused_rather_than_guessed_at(monkeypatch):
    """These files carry one sheet and the probe resolves it through the
    workbook relationships. If one ever carries two, reading whichever came
    first is a plausible count of the wrong thing."""
    buffer = io.BytesIO()
    cipsoc_workbook(buffer, {SHEET: [HEADER, ["0001", "x", "47-2111.00", "y"]],
                             "Notes": [["ignore me"]]})
    monkeypatch.setattr(probe, "download", lambda url, into: buffer.getvalue())
    with pytest.raises(probe.MalformedSource, match="refusing to guess which sheet"):
        probe.routes()


def test_the_onet_column_is_found_by_name_not_by_position(monkeypatch):
    """These files carry four columns today, and reading the third by index
    would keep working — wrongly — if a fifth arrived. The fixture puts the
    O*NET-SOC column somewhere else entirely."""
    moved = ["RAPIDS Code", "O*NET-SOC 2019 Code", "RAPIDS Title", "Notes"]
    crosswalks(monkeypatch,
               [moved, ["0001", "47-2111.00", "Electrician", "n/a"]],
               [moved, ["46.0302", "47-2111.00", "Electrician", "n/a"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})
    got = probe.routes()

    # The CODE, not the count. Asserting `== 1` passed under the mutation this
    # test exists to catch: with the column hardcoded to index 2 the probe read
    # "Electrician" as the occupation, which is still exactly one occupation.
    assert got["apprentice_soc_missing_from_ours"] == [], (
        "the O*NET-SOC column was read by position, so a reordered file "
        "yielded something that is not a SOC code at all")
    assert got["apprenticeable_in_ours"] == 1, (
        "the reordered file did not join against the crosswalk")


def test_a_row_that_omits_a_cell_does_not_shift_the_columns(monkeypatch):
    """Excel omits a blank cell rather than writing an empty one, so a row with
    no title arrives as `<c r="A5">…</c><c r="C5">…</c>`. A reader that appends
    in document order would read the O*NET-SOC *title* as its code, and every
    figure after that stays plausible and is wrong.

    This is why the probe uses `probe_cipsoc.rows`, which places cells by their
    `r` attribute, rather than carrying a reader of its own.
    """
    crosswalks(
        monkeypatch,
        [HEADER,
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         ["0002", "", "51-4081.00", "Machine Tool Setters"]],
        [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111", "51-4081"})

    got = probe.routes()
    assert got["apprentice_soc"] == 2, "the untitled row was dropped"
    assert got["apprenticeship_only"] == ["51-4081"], (
        "the untitled row's code was misread — the reader is placing cells by "
        "document order again")


def test_a_host_that_does_not_resolve_is_told_apart_from_one_that_refuses(monkeypatch):
    """The distinction the CareerOneStop page turns on, and the reason it can
    assert one finding and not the other.

    A name that resolves nowhere is broken at the publisher's end. A resolved
    address that refuses a connection cannot be told apart, from one network,
    from an outbound restriction. Reporting both as "unreachable" would let the
    page overclaim.
    """
    def resolve(host):
        if host == "gone.example":
            raise OSError(8, "nodename nor servname provided")
        return "10.0.0.1"
    monkeypatch.setattr(probe.socket, "gethostbyname", resolve)

    # `dig` too. This patched `gethostbyname` only, so `resolves_anywhere`
    # shelled out to the real `dig @8.8.8.8` for every host in REACH — real
    # network calls from a unit test, answering about the internet rather
    # than about the fixture.
    def dug(argv, *a, **k):
        host = argv[-1]
        answer = "" if host == "gone.example" else "10.0.0.1\n"
        return subprocess.CompletedProcess(argv, 0, stdout=answer, stderr="")
    monkeypatch.setattr(probe.subprocess, "run", dug)

    def refuse(*a, **k):
        raise probe.urllib.error.URLError("timed out")
    monkeypatch.setattr(probe.urllib.request, "urlopen", refuse)
    monkeypatch.setattr(probe, "REACH", [("gone", "https://gone.example/"),
                                         ("refusing", "https://refusing.example/")])

    by_name = {row["source"]: row for row in probe.reachable()}
    assert "does not resolve" in by_name["gone"]["status"]
    assert by_name["gone"]["dns"] is None
    assert "no connection" in by_name["refusing"]["status"], (
        "a refused connection is reported as a DNS failure — a claim the "
        "careeronestop page explicitly declines to make")
    assert by_name["refusing"]["dns"] == "10.0.0.1"


def test_the_no_match_sentinel_is_dropped_from_every_side(monkeypatch):
    """`99-9999` is not an occupation, and it was filtered on one set of three.

    `our_soc()` excluded it; `apprentice_soc` and `programme_soc` did not. A
    sentinel row in either O*NET crosswalk would have landed in the
    apprenticeship set, been absent from the programme set, and been reported
    as an occupation reachable ONLY by apprenticeship — which is the headline
    figure. Same class as edtech-kg#70 on the NCES file.
    """
    crosswalks(
        monkeypatch,
        [HEADER,
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         ["9999", "No match", "99-9999.00", "No match"]],
        [HEADER,
         ["46.0302", "Electrician", "47-2111.00", "Electricians"],
         ["99.9999", "No match", "99-9999.00", "No match"]])
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111"})

    got = probe.routes()
    assert got["apprentice_soc"] == 1, "the sentinel was counted as an occupation"
    assert got["programme_soc"] == 1
    assert got["apprenticeship_only"] == [], (
        "the sentinel was reported as an occupation reachable only by "
        "apprenticeship — the figure this whole page leads with")
    assert probe.NO_MATCH not in got["apprentice_soc_missing_from_ours"]


def test_a_name_that_resolves_nowhere_is_told_apart_from_one_this_network_cannot_see(monkeypatch):
    """The distinction both pages rest on, and it needs more than one resolver.

    `socket.gethostbyname()` alone answers "this network cannot resolve it".
    The page claims "no A record from ANY resolver", which is a claim about the
    publisher — so the probe asks the public resolvers too, and only makes the
    strong claim when every resolver it could ask said no.
    """
    monkeypatch.setattr(probe.socket, "gethostbyname",
                        lambda host: (_ for _ in ()).throw(OSError(8, "no")))

    # `probe.subprocess` is patched, so no real `dig @8.8.8.8` leaves the
    # machine. Without this the test queried Google's resolver for real — a
    # network call from a suite that is supposed to be hermetic, and an
    # assertion whose answer depended on someone else's DNS.
    asked = []

    def answer(cmd, **kw):
        asked.append(cmd)

        class Out:
            returncode = 0
            stdout = "" if any("gone.example" in c for c in cmd) else "10.0.0.1\n"
        return Out()
    monkeypatch.setattr(probe.subprocess, "run", answer)

    gone = probe.resolves_anywhere("gone.example")
    assert asked, "the public resolvers were never asked"
    assert all(cmd[0] == "dig" for cmd in asked), asked
    assert gone["resolves_nowhere"] is True
    assert set(gone["by_resolver"]) == {"system", "Google", "Cloudflare"}

    assert gone["by_resolver"] == {"system": None, "Google": None, "Cloudflare": None}, (
        f"the strong claim was made from something other than three negative "
        f"answers: {gone['by_resolver']}")

    local = probe.resolves_anywhere("fine.example")
    assert local["by_resolver"]["Google"] == "10.0.0.1"
    assert local["resolves_nowhere"] is False, (
        "a name the public resolvers DO know was reported as resolving "
        "nowhere — that is a claim about the publisher made from a local "
        "failure")


def test_a_resolver_that_cannot_be_asked_is_not_counted_as_a_no(monkeypatch):
    """"We could not ask" is not "there is no record". A machine without `dig`,
    or one that cannot reach 8.8.8.8, must not turn into evidence about a
    publisher."""
    monkeypatch.setattr(probe.socket, "gethostbyname",
                        lambda host: (_ for _ in ()).throw(OSError(8, "no")))

    def missing(cmd, **kw):
        raise FileNotFoundError("dig")
    monkeypatch.setattr(probe.subprocess, "run", missing)

    got = probe.resolves_anywhere("gone.example")
    assert got["by_resolver"]["Google"] == "unknown"
    assert got["resolves_nowhere"] is False, (
        "an unreachable resolver was read as a negative answer")


def test_the_anonymous_request_really_sends_no_user_agent(monkeypatch):
    """`urllib` inserts `Python-urllib/3.x` unless the header is cleared, so an
    "anonymous" arm measures a DEFAULT agent rather than an absent one — the
    trap edtech-kg#37 recorded on bls.gov, where the whole finding turned on
    which agent was sent.

    Both pages separate a block on anonymity from a block on automation, and
    that separation is only as good as this.
    """
    sent = []

    class R:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def capture(request, *a, **k):
        sent.append(request.get_header("User-agent"))
        return R()
    monkeypatch.setattr(probe.urllib.request, "urlopen", capture)

    probe.attempt("https://x.example/", probe.USER_AGENT)
    probe.attempt("https://x.example/", None)
    assert sent[0] == probe.USER_AGENT
    assert sent[1] == "", (
        f"the anonymous request sent {sent[1]!r} — urllib's default agent, "
        f"not an absent one")


def test_the_major_group_split_is_computed_not_typed(monkeypatch):
    """The half of this finding that was hand-typed.

    The trades table was measured in a shell and written into the document,
    under a heading promising every figure comes from the probe. The probe
    computes it now — and the claim it supports ("the exclusive set is not the
    trades") is arithmetic a reader can re-run.
    """
    crosswalks(
        monkeypatch,
        [HEADER,
         # Three construction occupations, two also reachable by a programme.
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         ["0002", "Plumber", "47-2152.00", "Plumbers"],
         ["0004", "Roofer", "47-2181.00", "Roofers"],
         # Two production occupations, both reachable no other way — so the
         # gap is 2 against 1 and the ORDER is falsifiable. It was 1 against
         # 1, and the assertion below read `1 >= 1 or ...`, which is true
         # however the list comes back: a test of the ordering that no
         # ordering could fail.
         ["0003", "Machine Setter", "51-4081.00", "Machine Tool Setters"],
         ["0005", "Machinist", "51-4041.00", "Machinists"]],
        [HEADER,
         ["46.0302", "Electrician", "47-2111.00", "Electricians"],
         ["46.0503", "Plumber", "47-2152.00", "Plumbers"]])
    monkeypatch.setattr(probe, "our_soc", lambda: set())

    # Called ONCE. It was called again at the end for the ordering, which
    # assumes it is side-effect free and re-mockable rather than asserting it.
    found = probe.routes()["by_major_group"]
    groups = {g["name"]: g for g in found}
    assert set(groups) == {"Construction and Extraction", "Production"}

    trades = groups["Construction and Extraction"]
    assert (trades["apprenticeable"], trades["also_via_a_programme"],
            trades["only_apprenticeship"]) == (3, 2, 1)
    assert trades["covered_pct"] == 67, (
        "the coverage percentage is not derived from the two counts beside it")

    production = groups["Production"]
    assert (production["apprenticeable"], production["only_apprenticeship"]) == (2, 2)
    assert production["covered_pct"] == 0

    # Ordered by the GAP, descending — which is what the section argues about,
    # and what the document's table is read off.
    assert [g["name"] for g in found] == ["Production", "Construction and Extraction"], (
        "the groups are not ordered by the exclusive count, so the document's "
        "table is in whatever order the SOC prefixes happen to sort in")


def test_json_does_not_force_the_slow_network_probe(monkeypatch):
    """`--json` turned `--reach` on, which made the machine-readable mode take
    the network path the help text says is off by default — a flag doing
    something its own documentation denies."""
    calls = []
    monkeypatch.setattr(probe, "probe",
                        lambda quiet, with_reach: calls.append(with_reach) or {})
    probe.main(["--json"])
    assert calls == [False], "--json still forces the reachability probe"
    calls.clear()
    probe.main(["--json", "--reach"])
    assert calls == [True], "--reach no longer turns it on"


def test_a_network_failure_fetching_the_crosswalk_is_refused_not_a_traceback(monkeypatch, tmp_path):
    """`our_soc()` caught `RuntimeError` and `ValueError` only.

    `probe_cipsoc.download()` raises `URLError` when the network is down, and
    that escaped `main()` as a traceback rather than arriving as `refused:` —
    the same class the `MalformedSource` wrapper exists to close, through the
    one door left open.
    """
    monkeypatch.setattr(probe.crosswalk, "LOCAL", tmp_path / "absent.xlsx")

    def offline(*a, **k):
        raise probe.urllib.error.URLError("network is unreachable")
    monkeypatch.setattr(probe.crosswalk, "download", offline)

    with pytest.raises(probe.MalformedSource, match="could not fetch the CIP-SOC"):
        probe.our_soc()


def test_the_two_programme_crosswalks_are_reported_apart_not_as_one(monkeypatch):
    """The page's headline was measured against the wrong crosswalk.

    `apprenticeship_only` is a set difference against **O*NET's** CIP-to-SOC
    file. The crosswalk this repo loads is NCES's, and the page published the
    first number under a sentence about the second: "63 of them are reachable
    no other way — this graph has no shape for those at all", while the probe's
    own join section printed 0 apprenticeship codes missing from our crosswalk.
    Both figures were on the page and they contradicted each other.

    So the fixture builds exactly that shape — an occupation O*NET's programme
    file misses and ours carries — and both differences are asserted. One key
    cannot stand in for the other again.
    """
    crosswalks(
        monkeypatch,
        [HEADER,
         ["0001", "Electrician", "47-2111.00", "Electricians"],
         ["0003", "Machine Setter", "51-4081.00", "Machine Tool Setters"]],
        # O*NET's programme crosswalk reaches only the electrician.
        [HEADER, ["46.0302", "Electrician", "47-2111.00", "Electricians"]])
    # Ours reaches both — which is the real situation, measured: all 63 of the
    # occupations O*NET's file misses are codes this repo already carries.
    monkeypatch.setattr(probe, "our_soc", lambda: {"47-2111", "51-4081"})

    got = probe.routes()

    assert got["apprenticeship_only"] == ["51-4081"], (
        "the disagreement with O*NET's programme crosswalk is not reported")
    assert got["apprenticeship_only_vs_ours"] == [], (
        "an occupation our own crosswalk reaches was reported as one no "
        "programme can reach — the two crosswalks are not the same file and "
        "the page cannot quote one under a sentence about the other")


def test_a_cname_or_a_message_from_dig_is_not_taken_as_an_address(monkeypatch):
    """`found[0]` took the first line that was not a name.

    `dig +short` prints a CNAME chain before the address, and on some failures
    prints a message instead. Whatever that first line said became the answer
    a resolver gave — and it appears on the page as the address the host
    resolves to, which is a measured claim.
    """
    def dug(argv, *a, **k):
        host = argv[-1]
        if host == "chained.example":
            out = "alias.cdn.example.\n93.184.216.34\n"
        elif host == "broken.example":
            out = ";; connection timed out; no servers could be reached\n"
        else:
            out = "10.0.0.1\n"
        return subprocess.CompletedProcess(argv, 0, stdout=out, stderr="")
    monkeypatch.setattr(probe.subprocess, "run", dug)
    monkeypatch.setattr(probe.socket, "gethostbyname", lambda h: "10.0.0.1")

    chained = probe.resolves_anywhere("chained.example")
    assert chained["by_resolver"]["Google"] == "93.184.216.34", (
        "a CNAME was reported as the resolved address")

    broken = probe.resolves_anywhere("broken.example")
    assert broken["by_resolver"]["Google"] is None, (
        "a dig error message was reported as an address")
