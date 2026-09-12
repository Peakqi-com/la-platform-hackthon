#!/usr/bin/env bash
# 在 EC2 上執行（provision.sh 透過 ssh 餵進來）：解開程式、裝後端、build 前端、寫 systemd 與 Caddy、預載範例。
# 前置：/tmp/ntpc-src.tgz（程式）、/tmp/ntpc.env（環境變數）、選用 /tmp/ntpc-data.tgz 或已 rsync 的 /opt/app/data。
# 對應 runbook 第 2–5 步；可重複執行。
set -euo pipefail
APP=/opt/app
cd "$APP"

echo "--- 程式"
tar xzf /tmp/ntpc-src.tgz -C "$APP" && rm -f /tmp/ntpc-src.tgz
if [[ -f /tmp/ntpc-data.tgz ]]; then echo "--- 資料包"; tar xzf /tmp/ntpc-data.tgz -C "$APP" && rm -f /tmp/ntpc-data.tgz; fi
mkdir -p data/cases data/audit data/cadastre/cases data/tiles
find "$APP" -path "$APP/frontend/node_modules" -prune -o \( -name "._*" -o -name ".DS_Store" \) -type f -print0 | xargs -0 -r rm -f   # macOS 打包夾帶的 AppleDouble 檔會被當 JSON 讀
cp /tmp/ntpc.env "$APP/.env" && chmod 600 "$APP/.env" && rm -f /tmp/ntpc.env
# shellcheck disable=SC1091
set -a; . "$APP/.env"; set +a

echo "--- 後端 venv"
cd backend
[[ -d .venv ]] || python3.12 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.lock || .venv/bin/pip install -q -e ".[llm]"
.venv/bin/pip install -q -e ".[llm]"

echo "--- 前端 build（BACKEND_URL 寫進 rewrites）"
cd ../frontend
npm ci --no-audit --no-fund --silent
BACKEND_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1 npm run build 2>&1 | tail -3
cd "$APP"

echo "--- systemd"
sudo tee /etc/systemd/system/ntpc-backend.service >/dev/null <<EOF
[Unit]
Description=ntpc appraisal backend (uvicorn)
After=network.target
[Service]
User=ubuntu
WorkingDirectory=$APP/backend
EnvironmentFile=$APP/.env
ExecStart=$APP/backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/systemd/system/ntpc-frontend.service >/dev/null <<EOF
[Unit]
Description=ntpc appraisal frontend (next start)
After=network.target ntpc-backend.service
[Service]
User=ubuntu
WorkingDirectory=$APP/frontend
Environment=NODE_ENV=production
ExecStart=/usr/bin/npx next start -p 3000 -H 127.0.0.1
Restart=always
RestartSec=3
[Install]
WantedBy=multi-user.target
EOF
sudo tee /etc/caddy/Caddyfile >/dev/null <<EOF
$PUBLIC_HOST {
    encode gzip
    handle /api/* {
        reverse_proxy 127.0.0.1:8000
    }
    handle {
        reverse_proxy 127.0.0.1:3000
    }
}
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now ntpc-backend ntpc-frontend caddy >/dev/null
sudo systemctl restart ntpc-backend ntpc-frontend caddy

echo "--- 等後端"
for i in $(seq 1 30); do curl -s -m 5 http://127.0.0.1:8000/api/health | grep -q '"ok":true' && break; sleep 3; [[ $i == 30 ]] && { sudo journalctl -u ntpc-backend -n 30 --no-pager; exit 1; }; done

echo "--- 預載範例案件"
for v in template tampered residential blank_survey; do curl -s -m 120 "http://127.0.0.1:8000/api/cases/demo?variant=$v&save=true" >/dev/null || true; done
if [[ -f backend/scripts/prebuild_walk.py && -e data/osm/walk.sqlite ]]; then echo "--- 預建步行圖快取"; (cd backend && .venv/bin/python scripts/prebuild_walk.py >/dev/null 2>&1 || true); fi

echo "--- 狀態"
systemctl is-active ntpc-backend ntpc-frontend caddy | paste -sd' ' -
curl -s -m 5 http://127.0.0.1:8000/api/health | head -c 200; echo
