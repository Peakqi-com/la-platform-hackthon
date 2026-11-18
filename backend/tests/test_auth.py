"""整站登入（app/auth.py）：沒帳密檔＝不設密碼；有帳號時 check 端點對頁面導登入頁、對 API 回 401（不帶 WWW-Authenticate）。"""
import pytest
from fastapi.testclient import TestClient

from app import auth as A
from app.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def with_user(tmp_path, monkeypatch):
    f = tmp_path / "site_auth"
    f.write_text(f"# 測試\nreviewer:{A.hash_password('correct-horse', iterations=1000)}\n", encoding="utf-8")
    monkeypatch.setenv("SITE_AUTH_FILE", str(f))
    A._fails.clear()
    return f


def test_disabled_without_file(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SITE_AUTH_FILE", str(tmp_path / "none"))
    assert client.get("/api/auth/check", headers={"x-forwarded-uri": "/dashboard"}).status_code == 200
    assert client.get("/api/auth/me").json() == {"enabled": False, "user": None}


def test_page_redirects_to_login(client, with_user):
    r = client.get("/api/auth/check", headers={"x-forwarded-uri": "/review?case=1", "x-forwarded-method": "GET"}, follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "/login?next=%2Freview%3Fcase%3D1"


def test_api_gets_401_without_basic_challenge(client, with_user):
    r = client.get("/api/auth/check", headers={"x-forwarded-uri": "/api/cases", "x-forwarded-method": "GET"})
    assert r.status_code == 401
    assert "www-authenticate" not in r.headers
    assert r.json()["login"] is True


def test_login_flow(client, with_user):
    assert client.post("/api/auth/login", json={"username": "reviewer", "password": "wrong"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "reviewer", "password": "correct-horse", "next": "/sheets?case=1"})
    assert r.status_code == 200 and r.json()["next"] == "/sheets?case=1"
    assert A.COOKIE in r.cookies
    assert client.get("/api/auth/check", headers={"x-forwarded-uri": "/dashboard"}).status_code == 200
    assert client.get("/api/auth/me").json() == {"enabled": True, "user": "reviewer"}
    client.post("/api/auth/logout")
    assert client.get("/api/auth/me").json()["user"] is None


def test_password_change_invalidates_sessions(with_user):
    tok = A.make_token("reviewer")
    assert A.verify_token(tok) == "reviewer"
    with_user.write_text(f"reviewer:{A.hash_password('another-pass', iterations=1000)}\n", encoding="utf-8")
    assert A.verify_token(tok) is None


def test_tampered_or_expired_token(with_user):
    tok = A.make_token("reviewer")
    u, exp, sig = tok.split(".")
    assert A.verify_token(f"{A._b64('admin')}.{exp}.{sig}") is None
    assert A.verify_token(tok, now=int(exp) + 1) is None


def test_rate_limit(client, with_user):
    for _ in range(A.MAX_FAILS):
        client.post("/api/auth/login", json={"username": "reviewer", "password": "x"})
    assert client.post("/api/auth/login", json={"username": "reviewer", "password": "correct-horse"}).status_code == 429


@pytest.mark.parametrize("nxt,expect", [("//evil.com", "/dashboard"), ("https://evil.com", "/dashboard"), ("/\\evil", "/dashboard"),
                                         ("/login?next=/x", "/dashboard"), (None, "/dashboard"), ("/review?case=2", "/review?case=2")])
def test_safe_next(nxt, expect):
    assert A.safe_next(nxt) == expect
