"""Retry policy toward the gazette (ARCH-014): Retry-After, jitter, budget."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from email.utils import format_datetime

import httpx
import pytest
import respx

from register_mcp import server as s

PATH = "/api/v1/publications"
URL = f"{s.GAZETTE_BASE}{PATH}"


def _resp(status: int, retry_after: str | None = None) -> httpx.Response:
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return httpx.Response(status, headers=headers, request=httpx.Request("GET", URL))


class TestParseRetryAfter:
    def test_delta_seconds(self):
        assert s.parse_retry_after(_resp(429, "120")) == 120.0

    def test_http_date_in_the_future(self):
        when = datetime.now(UTC) + timedelta(seconds=90)
        got = s.parse_retry_after(_resp(503, format_datetime(when, usegmt=True)))
        assert got is not None
        assert 80 <= got <= 95

    def test_http_date_in_the_past_means_now(self):
        when = datetime.now(UTC) - timedelta(hours=1)
        assert s.parse_retry_after(_resp(503, format_datetime(when, usegmt=True))) == 0.0

    def test_absent_header(self):
        assert s.parse_retry_after(_resp(503)) is None

    def test_malformed_header_does_not_raise(self):
        assert s.parse_retry_after(_resp(503, "next Tuesday")) is None
        assert s.parse_retry_after(_resp(503, "")) is None
        assert s.parse_retry_after(_resp(503, "-5")) is None

    def test_ignored_on_other_statuses(self):
        # 502 and 504 are retried but carry no promise about when to come back.
        assert s.parse_retry_after(_resp(502, "30")) is None

    def test_no_response_at_all(self):
        assert s.parse_retry_after(None) is None


class TestRetryDelay:
    def test_retry_after_beats_the_linear_curve(self):
        # attempt 1 with backoff 0.5 spans [0.25, 0.75]s — 9 must come from the header.
        assert (
            9.0
            <= s.gazette_retry_delay(1, _resp(503, "9"))
            <= 9.0 * (1 + s.GAZETTE_RETRY_AFTER_JITTER)
        )

    def test_retry_after_is_never_undercut(self):
        for _ in range(50):
            assert s.gazette_retry_delay(1, _resp(503, "5")) >= 5.0

    def test_absurd_retry_after_is_capped(self):
        # Exactly the cap: capping happens after jitter. Equality discriminates —
        # the bare curve would give 0.5s here.
        assert s.gazette_retry_delay(1, _resp(503, "86400")) == s.GAZETTE_MAX_DELAY_S

    def test_the_cap_is_a_real_bound_not_a_midpoint(self):
        """The cap must hold even when jitter swings up (Codex review, parlament#35)."""
        for attempt in range(1, s.GAZETTE_MAX_RETRIES + 1):
            for _ in range(20):
                assert s.gazette_retry_delay(attempt, None) <= s.GAZETTE_MAX_DELAY_S
                assert s.gazette_retry_delay(attempt, _resp(503, "86400")) <= s.GAZETTE_MAX_DELAY_S

    def test_delay_is_spread(self):
        draws = {s.gazette_retry_delay(2, None) for _ in range(30)}
        assert len(draws) > 1, "delay is deterministic — jitter is not applied"
        base = s.GAZETTE_RETRY_BACKOFF * 2
        assert all(
            base * (1 - s.GAZETTE_JITTER_SPREAD) <= d <= base * (1 + s.GAZETTE_JITTER_SPREAD)
            for d in draws
        )


@pytest.fixture
def fake_clock(monkeypatch):
    """A clock that only advances when the client sleeps.

    Without it the budget can never run out: patched-out sleeps take no
    wall-clock time, ``monotonic()`` never moves, and the test would pass
    whatever the budget logic did.
    """
    now = {"t": 1000.0}
    slept: list[float] = []

    async def _sleep(seconds):
        slept.append(seconds)
        now["t"] += seconds

    monkeypatch.setattr(s, "monotonic", lambda: now["t"])
    # Patch the module attribute, not ``asyncio.sleep``: the latter reaches
    # every import in the process, and a test that uses ``asyncio.sleep(0)`` to
    # yield to the event loop then stops testing anything while still passing.
    monkeypatch.setattr(s, "_sleep", _sleep)
    return slept


@respx.mock
async def test_retry_after_reaches_the_sleep(fake_clock):
    respx.get(URL).mock(side_effect=[_resp(503, "7"), httpx.Response(200, json={})])
    await s._gazette_get_json(PATH)
    assert len(fake_clock) == 1
    assert 7.0 <= fake_clock[0] <= 7.0 * (1 + s.GAZETTE_RETRY_AFTER_JITTER)


@respx.mock
async def test_404_still_fails_fast_without_waiting(fake_clock):
    """A non-transient status is a statement about the request, not the moment."""
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        await s._gazette_get_json(PATH)
    assert route.call_count == 1
    assert fake_clock == []


@respx.mock
async def test_budget_cuts_the_ladder_short(fake_clock):
    route = respx.get(URL).mock(return_value=_resp(503, "30"))
    with pytest.raises(httpx.HTTPStatusError):
        await s._gazette_get(PATH, total_budget=1.0)
    assert route.call_count < s.GAZETTE_MAX_RETRIES, "budget did not bound the ladder"
    assert route.call_count >= 1, "the first attempt must always go out"


@respx.mock
async def test_full_ladder_runs_when_the_budget_allows(fake_clock):
    """Counter-direction: a wide budget must not cut anything short."""
    route = respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(httpx.HTTPStatusError):
        await s._gazette_get(PATH, total_budget=600.0)
    assert route.call_count == s.GAZETTE_MAX_RETRIES


@respx.mock
async def test_text_and_json_share_one_retry_core(fake_clock):
    """Both wrappers must go through the same loop — the policy lives in one place."""
    respx.get(URL).mock(side_effect=[_resp(503, "1"), httpx.Response(200, text="<xml/>")])
    assert await s._gazette_get_text(PATH) == "<xml/>"
    assert len(fake_clock) == 1


@respx.mock
async def test_a_slow_response_is_cut_by_the_wall_clock_deadline():
    """The budget must bind even when the httpx timeout never fires.

    httpx applies its timeout per operation and the read timeout restarts with
    every chunk, so a slowly trickling response can outlast the total budget
    without any single read timing out. Hence a real ``asyncio.timeout``.

    Deliberately without ``fake_clock``: this guarantee is about real time, and
    a clock that only moves when something sleeps could not refute it.
    """
    import asyncio as real_asyncio
    import time as real_time

    async def _slow(request):
        await real_asyncio.sleep(1.0)
        return httpx.Response(200, json={})

    respx.get(URL).mock(side_effect=_slow)
    started = real_time.monotonic()
    with pytest.raises(TimeoutError):
        await s._gazette_get(PATH, total_budget=0.05)
    elapsed = real_time.monotonic() - started
    assert elapsed < 0.5, f"deadline did not cut: {elapsed:.2f}s"


def test_default_budget_stays_under_the_mcp_client_default():
    from mcp.shared._httpx_utils import MCP_DEFAULT_TIMEOUT

    assert s.GAZETTE_TOTAL_BUDGET_S < MCP_DEFAULT_TIMEOUT


# --- Netzwerkfehler und Timeouts (ARCH-014, Nachzug) ------------------------
#
# Bisher deckte die Schleife nur Status-Codes ab. Ein 503 aus einem Ausfall
# bekam drei Versuche, eine abgelehnte Verbindung aus *demselben* Ausfall
# keinen einzigen — der Retry sah vorhanden aus und liess den haeufigsten Fall
# ungedeckt. Genau diese Form von Ausfall hat am 1. August in swiss-efv-mcp
# vier Live-Tests gekippt.


class TestNetworkErrorsAreRetried:
    @respx.mock
    async def test_a_connect_error_is_retried(self, fake_clock):
        route = respx.get(URL).mock(
            side_effect=[httpx.ConnectError(""), httpx.Response(200, json={"ok": 1})]
        )
        assert await s._gazette_get_json(PATH) == {"ok": 1}
        assert route.call_count == 2

    @respx.mock
    async def test_a_read_timeout_is_retried(self, fake_clock):
        route = respx.get(URL).mock(
            side_effect=[httpx.ReadTimeout(""), httpx.Response(200, json={"ok": 1})]
        )
        await s._gazette_get_json(PATH)
        assert route.call_count == 2

    @respx.mock
    async def test_network_errors_exhaust_the_attempts_and_surface_the_cause(self, fake_clock):
        """Der letzte Fehler wird durchgereicht, nicht verpackt (OBS-007).

        ``httpx.ConnectError`` traegt ein leeres ``str()`` — der Typ ist das
        Einzige, was die Meldung noch traegt, und er muss deshalb ueberleben.
        """
        route = respx.get(URL).mock(side_effect=httpx.ConnectError(""))
        with pytest.raises(httpx.ConnectError):
            await s._gazette_get_json(PATH)
        assert route.call_count == s.GAZETTE_MAX_RETRIES

    @respx.mock
    async def test_a_network_error_waits_between_attempts(self, fake_clock):
        """Ohne Wartezeit waeren drei Versuche bloss drei sofortige Fehlschlaege."""
        respx.get(URL).mock(side_effect=[httpx.ConnectError(""), httpx.Response(200, json={})])
        await s._gazette_get_json(PATH)
        assert len(fake_clock) == 1
        assert fake_clock[0] > 0.0


# --- 429 ---------------------------------------------------------------------


class TestRateLimitIsRetried:
    @respx.mock
    async def test_a_429_is_retried(self, fake_clock):
        """Ein 429 nennt seine eigene Wiederkehrzeit — der einzige Status, der das tut."""
        route = respx.get(URL).mock(side_effect=[_resp(429, "3"), httpx.Response(200, json={})])
        await s._gazette_get_json(PATH)
        assert route.call_count == 2

    @respx.mock
    async def test_the_retry_after_of_a_429_reaches_the_sleep(self, fake_clock):
        """Vorher wurde der Header gelesen und dann nie benutzt.

        ``parse_retry_after`` kannte 429 bereits, ``_TRANSIENT_STATUS`` nicht —
        der geparste Wert lief also ins Leere und der Aufruf scheiterte sofort.
        """
        respx.get(URL).mock(side_effect=[_resp(429, "6"), httpx.Response(200, json={})])
        await s._gazette_get_json(PATH)
        assert len(fake_clock) == 1
        assert 6.0 <= fake_clock[0] <= 6.0 * (1 + s.GAZETTE_RETRY_AFTER_JITTER)

    @respx.mock
    async def test_a_400_is_still_not_retried(self, fake_clock):
        """Die Erweiterung darf 4xx nicht pauschal wiederholbar machen."""
        route = respx.get(URL).mock(return_value=httpx.Response(400))
        with pytest.raises(httpx.HTTPStatusError):
            await s._gazette_get_json(PATH)
        assert route.call_count == 1
        assert fake_clock == []


# --- Budget bindet auch den Netzwerkpfad ------------------------------------


@respx.mock
async def test_a_network_error_does_not_outlive_the_budget(fake_clock, monkeypatch):
    """Eine Wartezeit, die das Budget ueberdauert, wird nicht angetreten."""
    monkeypatch.setattr(s, "GAZETTE_RETRY_BACKOFF", 3600.0)
    monkeypatch.setattr(s, "GAZETTE_MAX_DELAY_S", 3600.0)
    route = respx.get(URL).mock(side_effect=httpx.ConnectError(""))
    with pytest.raises(httpx.ConnectError):
        await s._gazette_get(PATH, total_budget=1.0)
    assert route.call_count == 1, "nach dem ersten Fehler blieb keine Zeit mehr"
    # Der Aufrufzaehler allein trennt die Entwuerfe nicht: Ohne den Check wird
    # die 3600-s-Wartezeit *angetreten*, die Uhr springt ueber die Deadline und
    # die Schleife bricht danach genauso nach einem Request ab. Beobachtbar ist
    # nur, ob ueberhaupt gewartet wurde.
    assert fake_clock == [], "eine Wartezeit jenseits des Budgets wurde angetreten"


async def test_an_exhausted_budget_names_the_budget_and_the_endpoint():
    """OBS-007: Ein nackter ``TimeoutError`` nennt weder Budget noch Pfad."""
    with pytest.raises(TimeoutError, match=r"budget of .*publications"):
        await s._gazette_get(PATH, total_budget=-1.0)
