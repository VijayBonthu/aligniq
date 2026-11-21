"""OAuth popup returns the token to the allowed frontend origin that started the login.

During the move from grounded-iq.com to aligniq.grounded-iq.com both hosts serve the SPA
(founder, 2026-11-20). The login endpoint records which allowed origin opened the popup
(Referer of the window.open navigation, or an explicit ?origin=), keeps it in the OAuth
state (a signed claim for GitHub/Microsoft, the server-side auth_states value for Google),
and the callback page posts the access token to that origin. Anything not on the
CORS_ORIGINS allow-list falls back to FRONTEND_URL, and a tampered state is rejected.
"""
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from jose import jwt
from starlette.requests import Request

import routers.authentication as auth

OLD = "https://grounded-iq.com"
NEW = "https://aligniq.grounded-iq.com"


def run_async(coro):
    # Same convention as test_oauth_login.py: reuse the current loop.
    return asyncio.get_event_loop().run_until_complete(coro)


def make_request(path, query="", headers=None):
    scope = {
        "type": "http",
        "method": "GET",
        "scheme": "https",
        "server": ("api.grounded-iq.com", 443),
        "client": ("203.0.113.7", 50000),
        "path": path,
        "query_string": query.encode(),
        "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
    }
    return Request(scope)


def posted_origin(html: str) -> str:
    """The targetOrigin literal the popup page passes to window.opener.postMessage."""
    tail = html.split("postMessage(", 1)[1]
    close = tail.index(");")
    return tail[:close].rstrip().rsplit("'", 2)[-2]


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setattr(auth.settings, "SECRET_KEY_J", "unit-test-secret-key", raising=False)
    monkeypatch.setattr(auth.settings, "ALGORITHM", "HS256", raising=False)
    monkeypatch.setattr(auth.settings, "COOKIE_DOMAIN", ".grounded-iq.com", raising=False)
    monkeypatch.setattr(auth.settings, "COOKIE_SECURE", True, raising=False)
    monkeypatch.setattr(auth, "FRONTEND_ORIGIN", OLD)
    monkeypatch.setenv("CORS_ORIGINS", f"{OLD},{NEW}")

    async def fake_ip(request):
        return "203.0.113.7"

    async def fake_user(*a, **k):
        return SimpleNamespace(user_id="u1")

    monkeypatch.setattr(auth, "get_client_ip", fake_ip)
    monkeypatch.setattr(auth, "get_or_create_oauth_user", fake_user)
    monkeypatch.setattr(auth, "_issue_session", lambda user, db, login_provider=None: ("access-tok", "raw-refresh"))


# Calls FakeGitHub saw: ("authorize", state) and ("token", code).
GH_CALLS = []


class FakeGitHub:
    """Captures the state the login endpoint signs; never calls GitHub."""

    async def get_authorization_url(self, state):
        GH_CALLS.append(("authorize", state))
        return "https://github.com/login/oauth/authorize?state=" + state, state

    async def get_access_token(self, code):
        GH_CALLS.append(("token", code))
        return "gh-token"

    async def get_user_info(self, token):
        return {"id": "1", "email": "ada@acme.com", "verified_email": True}


def github_state_from_login(monkeypatch, request):
    GH_CALLS.clear()
    monkeypatch.setattr(auth, "GitHubOAuth", FakeGitHub)
    run_async(auth.github_login(request))
    return GH_CALLS[-1][1]


# ---------------------------------------------------------------------------
# An allowed origin is returned to
# ---------------------------------------------------------------------------
def test_github_login_from_new_host_posts_token_to_new_host(monkeypatch):
    state = github_state_from_login(
        monkeypatch, make_request("/api/v1/auth/github/login", headers={"Referer": NEW + "/"}))
    assert jwt.decode(state, "unit-test-secret-key", algorithms=["HS256"])["origin"] == NEW

    resp = run_async(auth.github_callback(
        make_request("/api/v1/auth/github/callback", f"code=c1&state={state}"), db=None))
    html = resp.body.decode()
    assert "github_auth_success" in html and "access-tok" in html
    assert posted_origin(html) == NEW
    # The refresh cookie is unchanged: httpOnly, Secure, scoped to .grounded-iq.com.
    cookie = resp.headers["set-cookie"]
    assert "Domain=.grounded-iq.com" in cookie and "HttpOnly" in cookie and "Secure" in cookie
    assert "raw-refresh" not in html


def test_google_login_records_origin_and_callback_posts_there(monkeypatch):
    monkeypatch.setattr(auth.flow, "authorization_url", lambda **k: ("https://accounts.google.com/o?x", "g-state-1"))
    run_async(auth.login(make_request("/api/v1/auth/login", headers={"Referer": NEW + "/login"})))
    assert auth.auth_states["g-state-1"] == NEW

    monkeypatch.setattr(auth, "auth_callback",
                        lambda url: {"message": "Authentication successful", "user": {}, "provider": "Google"})
    resp = run_async(auth.callback(
        make_request("/api/v1/auth/callback", "state=g-state-1&code=c"), db=None))
    assert posted_origin(resp.body.decode()) == NEW
    assert "g-state-1" not in auth.auth_states  # still single-use


def test_microsoft_round_trip_keeps_nonce_binding_and_returns_to_new_host(monkeypatch):
    seen = {}

    class FakeMicrosoft:
        async def get_authorization_url(self, state, nonce):
            seen["state"], seen["nonce"] = state, nonce
            return "https://login.microsoftonline.com/common/oauth2/v2.0/authorize", state

        async def get_access_token(self, code):
            return {"access_token": "ms-token", "id_token": "x"}

        async def get_user_info(self, token_response, expected_nonce=None):
            seen["expected_nonce"] = expected_nonce
            return {"id": "1", "email": "ada@acme.com", "verified_email": True}

    monkeypatch.setattr(auth, "MicrosoftOAuth", FakeMicrosoft)
    run_async(auth.microsoft_login(
        make_request("/api/v1/auth/microsoft/login", headers={"Referer": NEW + "/login"})))
    claims = jwt.decode(seen["state"], "unit-test-secret-key", algorithms=["HS256"])
    assert claims["origin"] == NEW and claims["nonce"] == seen["nonce"]

    resp = run_async(auth.microsoft_callback(
        make_request("/api/v1/auth/microsoft/callback", f"code=c1&state={seen['state']}"), db=None))
    html = resp.body.decode()
    assert "microsoft_auth_success" in html and posted_origin(html) == NEW
    assert seen["expected_nonce"] == seen["nonce"]  # id_token replay guard unchanged


def test_explicit_origin_param_wins_and_old_host_still_works(monkeypatch):
    req = make_request("/api/v1/auth/login", f"origin={NEW}", headers={"Referer": OLD + "/"})
    assert auth._login_start_origin(req) == NEW
    assert auth._login_start_origin(make_request("/x", headers={"Referer": OLD + "/login"})) == OLD
    # No Referer and no param (e.g. a privacy extension strips it): FRONTEND_URL.
    assert auth._login_start_origin(make_request("/x")) == OLD


# ---------------------------------------------------------------------------
# A disallowed origin falls back to FRONTEND_URL
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("candidate", [
    "https://evil.com",
    "https://grounded-iq.com.evil.com",       # suffix lookalike
    "https://evilaligniq.grounded-iq.com",    # prefix lookalike
    "http://aligniq.grounded-iq.com",         # scheme differs
    "https://aligniq.grounded-iq.com:8443",   # port differs
    "https://aligniq.grounded-iq.com@evil.com",
    "https://evil.com\\@aligniq.grounded-iq.com",
    "javascript:alert(1)",
    "*",
    "null",
    "",
])
def test_disallowed_origin_falls_back_to_frontend_url(monkeypatch, candidate):
    req = make_request("/api/v1/auth/github/login", headers={"Referer": candidate} if candidate else None)
    assert auth._login_start_origin(req) == OLD
    state = github_state_from_login(monkeypatch, req)
    resp = run_async(auth.github_callback(
        make_request("/api/v1/auth/github/callback", f"code=c1&state={state}"), db=None))
    assert posted_origin(resp.body.decode()) == OLD


def test_wildcard_cors_entry_never_widens_and_stored_value_is_rechecked(monkeypatch):
    monkeypatch.setenv("CORS_ORIGINS", "*")
    assert auth._resolve_frontend_origin("https://evil.com") == OLD
    # A Google auth_states value is re-checked at callback time, so one that is not on the
    # allow-list (here NEW, now that CORS_ORIGINS no longer lists it) is not trusted.
    auth.auth_states["g-state-2"] = NEW
    monkeypatch.setattr(auth, "auth_callback",
                        lambda url: {"message": "Authentication successful", "user": {}, "provider": "Google"})
    resp = run_async(auth.callback(
        make_request("/api/v1/auth/callback", "state=g-state-2&code=c"), db=None))
    assert posted_origin(resp.body.decode()) == OLD


# ---------------------------------------------------------------------------
# A tampered state is rejected
# ---------------------------------------------------------------------------
def test_tampered_state_is_rejected_and_never_steers_the_token(monkeypatch):
    state = github_state_from_login(
        monkeypatch, make_request("/api/v1/auth/github/login", headers={"Referer": NEW + "/"}))
    header, _payload, sig = state.split(".")
    forged_payload = jwt.encode(
        {**jwt.decode(state, "unit-test-secret-key", algorithms=["HS256"]), "origin": "https://evil.com"},
        "unit-test-secret-key", algorithm="HS256").split(".")[1]
    tampered = f"{header}.{forged_payload}.{sig}"  # new payload, old signature
    other_key = jwt.encode({"purpose": "oauth_login", "provider": "github", "origin": NEW},
                           "attacker-key", algorithm="HS256")

    for bad in (tampered, other_key):
        with pytest.raises(HTTPException) as exc:
            auth._read_login_state(bad, "github")
        assert exc.value.status_code == 401

        GH_CALLS.clear()
        resp = run_async(auth.github_callback(
            make_request("/api/v1/auth/github/callback", f"code=c1&state={bad}"), db=None))
        html = resp.body.decode()
        assert "github_auth_error" in html and "access-tok" not in html
        assert posted_origin(html) == OLD  # error goes to FRONTEND_URL, never the claim
        assert ("token", "c1") not in GH_CALLS  # code never exchanged
        assert "set-cookie" not in resp.headers

    # Google: a state the server never issued is refused before any token exchange.
    with pytest.raises(HTTPException) as exc:
        run_async(auth.callback(make_request("/api/v1/auth/callback", "state=forged&code=c"), db=None))
    assert exc.value.status_code == 401
