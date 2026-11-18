#!/usr/bin/env bash
# 在 EC2 上執行：設定整站登入帳號，並把 Caddy 換成「網站登入頁」（app/auth.py，forward_auth）。可重複執行。
#
#   /opt/app/deploy/site_auth.sh <帳號>               # 互動輸入密碼（或先 export SITE_AUTH_PASSWORD='…'）
#   /opt/app/deploy/site_auth.sh --caddy-only         # 只更新 Caddyfile（舊站從 basic auth 遷移）
#
# 帳號存在 /opt/app/.site_auth（pbkdf2 雜湊、權限 600、不進 git）；改檔即生效，不必重啟後端。
# 刪帳號：cd /opt/app/backend && .venv/bin/python -m app.auth remove <帳號>；全部刪光＝不設密碼。
set -euo pipefail
APP="${APP:-/opt/app}"
arg="${1:?用法：site_auth.sh <帳號> | --caddy-only}"

curl -sf -m 5 http://127.0.0.1:8000/api/auth/me >/dev/null || { echo "後端還沒有登入端點（/api/auth/me）：先等自動部署更新後端再執行" >&2; exit 1; }
if [[ "$arg" != "--caddy-only" ]]; then
  (cd "$APP/backend" && .venv/bin/python -m app.auth add "$arg")
fi

CF=/etc/caddy/Caddyfile
HOST="$(grep -m1 -E '^[^#[:space:]].*\{[[:space:]]*$' "$CF" | sed -E 's/[[:space:]]*\{[[:space:]]*$//')"
[[ -n "$HOST" ]] || { echo "讀不到 $CF 的站台名稱" >&2; exit 1; }
ts="$(date +%Y%m%d%H%M%S)"
sudo cp "$CF" "$CF.bak.$ts"
sudo tee "$CF.new" >/dev/null <<CADDY
$HOST {
    encode gzip
    # 整站登入：每個請求先問後端 /api/auth/check（app/auth.py）；帳號存在 $APP/.site_auth，沒有帳號＝不設密碼。
    @needlogin not path /api/health /api/auth/* /login /_next/* /favicon.ico
    forward_auth @needlogin 127.0.0.1:8000 {
        uri /api/auth/check
    }
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
CADDY
if ! sudo caddy validate --config "$CF.new" --adapter caddyfile >/dev/null; then
  sudo caddy validate --config "$CF.new" --adapter caddyfile || true
  sudo rm -f "$CF.new"; echo "Caddyfile 驗證失敗，未變更（原檔備份 $CF.bak.$ts）" >&2; exit 1
fi
sudo mv "$CF.new" "$CF"
for f in /etc/caddy/auth*.caddy; do [[ -e "$f" ]] && sudo mv "$f" "$f.disabled.$ts"; done   # 舊的 basic auth 片段停用（保留備份）
sudo systemctl reload caddy
echo "完成：$HOST 改用網站登入頁（備份 $CF.bak.$ts）"
(cd "$APP/backend" && .venv/bin/python -m app.auth list)
