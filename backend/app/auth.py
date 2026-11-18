"""
整站登入（取代 Caddy basic auth）。

為什麼不用 basic auth：機關電腦的 Chrome／Edge 常以群組原則 AuthSchemes 只允許 ntlm、negotiate，
瀏覽器收到 401 + WWW-Authenticate: Basic 不會彈出帳密視窗，直接顯示「HTTP ERROR 401」。
改成網站自己的登入頁（表單 → cookie），不依賴瀏覽器的認證機制。

運作：
  - 帳密檔 SITE_AUTH_FILE（預設 <repo>/.site_auth，不進 git），一行一個帳號：`帳號:pbkdf2_sha256$迭代$鹽$雜湊`。
    **沒有這個檔（或檔內沒有帳號）＝不設密碼**，本機開發照舊。
  - Caddy `forward_auth` 每個請求先問 GET /api/auth/check：
      cookie 有效 → 200；頁面請求 → 302 到 /login?next=原網址；API 請求 → 401 JSON（不帶 WWW-Authenticate，瀏覽器不會彈窗）。
  - POST /api/auth/login 驗帳密 → 設 HttpOnly cookie；POST /api/auth/logout 清 cookie；GET /api/auth/me 給前端顯示。
  - cookie = 帳號.到期時間.HMAC 簽章；簽章金鑰由 SITE_AUTH_SECRET（選用）加上帳密檔內容導出，
    所以改密碼或刪帳號後，舊的登入全部失效。

產生／更新帳號（在伺服器上）：
  cd /opt/app/backend && .venv/bin/python -m app.auth add <帳號>      # 互動輸入密碼
  .venv/bin/python -m app.auth remove <帳號>
  .venv/bin/python -m app.auth list
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import sys
import threading
import time
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parents[2]
COOKIE = "ntpc_session"
ITERATIONS = 200_000
MAX_FAILS = 10            # 同一來源 10 分鐘內失敗上限
FAIL_WINDOW = 600.0

_lock = threading.Lock()
_cache: dict = {"key": None, "users": {}, "secret": b""}
_fails: dict[str, list[float]] = {}


def auth_file() -> Path:
    return Path(os.environ.get("SITE_AUTH_FILE") or (REPO_DIR / ".site_auth"))


def session_days() -> float:
    try:
        return float(os.environ.get("SITE_AUTH_DAYS", "7"))
    except ValueError:
        return 7.0


# ---------------------------------------------------------------- 密碼雜湊

def hash_password(password: str, salt: str | None = None, iterations: int = ITERATIONS) -> str:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${dk.hex()}"


def check_password(password: str, stored: str) -> bool:
    try:
        algo, it, salt, digest = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), int(it))
        return hmac.compare_digest(dk.hex(), digest)
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------- 帳密檔

def _parse(text: str) -> dict[str, str]:
    users: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        name, h = line.split(":", 1)
        if name.strip() and h.strip():
            users[name.strip()] = h.strip()
    return users


def _load() -> tuple[dict[str, str], bytes]:
    """帳密檔依 mtime 快取；改檔即生效，不必重啟。"""
    p = auth_file()
    try:
        st = p.stat()
        key = (str(p), st.st_mtime_ns, st.st_size)
    except OSError:
        return {}, b""
    with _lock:
        if _cache["key"] != key:
            raw = p.read_bytes()
            _cache["users"] = _parse(raw.decode("utf-8", "replace"))
            env_secret = os.environ.get("SITE_AUTH_SECRET", "").encode("utf-8")
            _cache["secret"] = hashlib.sha256(b"ntpc-session\0" + env_secret + b"\0" + raw).digest()
            _cache["key"] = key
        return _cache["users"], _cache["secret"]


def enabled() -> bool:
    return bool(_load()[0])


# ---------------------------------------------------------------- session cookie

def _b64(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _unb64(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8")


def make_token(user: str, now: float | None = None) -> str:
    _, secret = _load()
    exp = int((now or time.time()) + session_days() * 86400)
    body = f"{_b64(user)}.{exp}"
    sig = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
    return f"{body}.{sig}"


def verify_token(token: str | None, now: float | None = None) -> str | None:
    """有效回帳號，否則 None。帳號已被刪除也算無效。"""
    if not token:
        return None
    users, secret = _load()
    try:
        u64, exp, sig = token.split(".")
        body = f"{u64}.{exp}"
        good = hmac.new(secret, body.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(good, sig) or int(exp) < (now or time.time()):
            return None
        user = _unb64(u64)
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    return user if user in users else None


def login(user: str, password: str) -> str | None:
    users, _ = _load()
    stored = users.get(user)
    if stored is None:
        hash_password(password)          # 帳號不存在也花一樣的時間，不洩漏帳號是否存在
        return None
    return make_token(user) if check_password(password, stored) else None


# ---------------------------------------------------------------- 失敗次數限制

def too_many_fails(client: str, now: float | None = None) -> bool:
    now = now or time.time()
    with _lock:
        lst = [t for t in _fails.get(client, []) if now - t < FAIL_WINDOW]
        _fails[client] = lst
        return len(lst) >= MAX_FAILS


def record_fail(client: str, now: float | None = None) -> None:
    with _lock:
        _fails.setdefault(client, []).append(now or time.time())


def clear_fails(client: str) -> None:
    with _lock:
        _fails.pop(client, None)


def safe_next(nxt: str | None) -> str:
    """登入後導回的位置只接受站內路徑（防開放式重新導向）。"""
    if not nxt or not nxt.startswith("/") or nxt.startswith("//") or "\\" in nxt or nxt.startswith("/login"):
        return "/dashboard"
    return nxt


# ---------------------------------------------------------------- 命令列：管理帳號

def _write(users: dict[str, str]) -> None:
    p = auth_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# 整站登入帳密（app/auth.py）。由 `python -m app.auth add <帳號>` 產生，勿手改雜湊。"]
    lines += [f"{u}:{h}" for u, h in users.items()]
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(p)


def _main(argv: list[str]) -> int:
    import getpass
    p = auth_file()
    users = _parse(p.read_text(encoding="utf-8")) if p.exists() else {}
    cmd = argv[0] if argv else ""
    if cmd == "add" and len(argv) == 2:
        name = argv[1].strip()
        if not name or ":" in name or any(c.isspace() for c in name):
            print("帳號不可空白、不可含冒號或空白", file=sys.stderr)
            return 2
        pw = os.environ.get("SITE_AUTH_PASSWORD") or getpass.getpass(f"{name} 的密碼：")
        if not os.environ.get("SITE_AUTH_PASSWORD") and getpass.getpass("再輸入一次：") != pw:
            print("兩次密碼不同", file=sys.stderr)
            return 2
        if len(pw) < 8:
            print("密碼至少 8 個字元", file=sys.stderr)
            return 2
        users[name] = hash_password(pw)
        _write(users)
        print(f"已設定帳號 {name}（{p}）；既有的登入全部失效")
        return 0
    if cmd == "remove" and len(argv) == 2:
        if users.pop(argv[1], None) is None:
            print(f"沒有帳號 {argv[1]}", file=sys.stderr)
            return 1
        _write(users)
        print(f"已刪除帳號 {argv[1]}；剩 {len(users)} 個" + ("（沒有帳號＝不設密碼）" if not users else ""))
        return 0
    if cmd == "list":
        print(f"{p}：" + ("、".join(users) if users else "沒有帳號（不設密碼）"))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
