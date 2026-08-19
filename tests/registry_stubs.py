"""Shared stubs for the Registry probe tests.

Split out when tests/test_probe_registry.py passed 500 lines and the reviewer
could no longer read it in one pass. Two files, one subject each: the totals
reconciliation (#59) and the course sampling (#53).
"""

import io
import json
import urllib.error
import urllib.parse

from etl import probe_registry as probe


def stub(monkeypatch, payload: bytes, x_total: int | None = None):
    class R:
        headers = {"x-total": str(x_total)} if x_total is not None else {}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return payload
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *a, **k: R())


def headers_stub(monkeypatch, table, root=None):
    """Serve x-total per path, and the API root as JSON."""
    class R:
        def __init__(self, h=None, body=b""): self.headers, self._b = h or {}, body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b

    def urlopen(request, *a, **k):
        url = request.full_url
        path = url[len(probe.REGISTRY):].split("?")[0]
        if request.get_method() == "HEAD":
            value = table.get(url) if url in table else table.get(path)
            if value == 401:
                raise urllib.error.HTTPError(url, 401, "no", {}, io.BytesIO(b""))
            return R({"x-total": str(value)} if value is not None else {})
        return R(body=json.dumps(root or {"total_envelopes": 10}).encode())

    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)


def paged(monkeypatch, by_page: dict, x_total: int = 47861):
    """A stub that varies by page, so multi-page accumulation is real.

    An earlier stub ignored the URL, so every page returned the same body and a
    12-page walk was indistinguishable from reading one page twelve times.
    """
    class R:
        def __init__(self, body): self._b, self.headers = body, {"x-total": str(x_total)}
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._b

    def urlopen(request, *a, **k):
        # Parsed properly rather than by string search: "per_page=" contains
        # "page=", and splitting on it silently read page 50 instead of page 1.
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        page = int(query.get("page", ["1"])[0])
        return R(json.dumps(by_page.get(page, [])).encode())
    monkeypatch.setattr(probe.urllib.request, "urlopen", urlopen)


def course(**extra):
    return {"decoded_resource": {"@type": "ceterms:Course", **extra}}


def prereq(description="PSYC101"):
    return {"ceterms:requires": [{"ceterms:name": {"en-US": "Prerequisites"},
                                  "ceterms:description": {"en-US": description}}]}
