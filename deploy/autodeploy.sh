#!/usr/bin/env bash
# EC2 自動部署（拉取式）：systemd timer 每 60 秒執行 `autodeploy.sh run`，GitHub 的 main 有新 commit 就
# 拉下來、依變更重裝／重建、重啟服務；健康檢查失敗自動回滾到前一個 commit。不需開任何入站埠，也不需 AWS 金鑰。
#
#   sudo -u ubuntu /opt/app/deploy/autodeploy.sh install   # 第一次：把 /opt/app 變成 git 工作樹、產 deploy key、裝 timer；印出公鑰
#   /opt/app/deploy/autodeploy.sh run                       # timer 呼叫；也可手動跑
#   /opt/app/deploy/autodeploy.sh status                    # 目前 commit、timer 狀態、最近 10 筆紀錄
#   /opt/app/deploy/autodeploy.sh rebuild                   # 對目前 HEAD 完整重裝依賴、重建前端、重啟
#
# 可調：DEPLOY_BRANCH（預設 main）、REPO（預設 git@github.com:Peakqi-com/la-platform-hackthon.git）
# 紀錄：/opt/app/deploy.log。data/、.env、backend/.venv、frontend/node_modules、.next 都不在 git 追蹤內，reset 不會動到。
set -euo pipefail
APP="${APP:-/opt/app}"
BRANCH="${DEPLOY_BRANCH:-main}"
REPO="${REPO:-git@github.com:Peakqi-com/la-platform-hackthon.git}"
LOG="$APP/deploy.log"
cd "$APP"
log() { echo "$(date '+%F %T') $*" | tee -a "$LOG"; }

health_ok() { for _ in $(seq 1 30); do curl -s -m 5 http://127.0.0.1:8000/api/health | grep -q '"ok":true' && curl -s -m 5 -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/ | grep -q '^200$' && return 0; sleep 3; done; return 1; }

build_frontend() {
  (cd frontend && set -o pipefail && BACKEND_URL=http://127.0.0.1:8000 NEXT_TELEMETRY_DISABLED=1 npm run build 2>&1 | tail -2 | sed 's/^/    /')
}

apply() {   # $1=舊 commit（none＝第一次）、$2=新 commit；依變更檔案決定要做什麼
  local old="$1" new="$2" changed
  # 第一次（工作樹來自 tarball，內容未必等於 repo）視為全部有變：重裝依賴、重建前端
  if [[ "$old" == none ]]; then changed="$(git ls-tree -r --name-only "$new")"; else changed="$(git diff --name-only "$old" "$new")"; fi
  git reset -q --hard "$new" || return 1
  find "$APP" -path "$APP/frontend/node_modules" -prune -o \( -name '._*' -o -name '.DS_Store' \) -type f -print0 | xargs -0 -r rm -f
  if grep -qE '^backend/(pyproject\.toml|requirements\.lock)$' <<<"$changed"; then
    log "  後端依賴有變 → pip install"; (cd backend && (.venv/bin/pip install -q -r requirements.lock || true) && .venv/bin/pip install -q -e ".[llm]") || { log "  pip install 失敗"; return 1; }
  fi
  if grep -qE '^frontend/package(-lock)?\.json$' <<<"$changed"; then
    log "  前端依賴有變 → npm ci"; (cd frontend && npm ci --no-audit --no-fund --silent) || { log "  npm ci 失敗"; return 1; }
  fi
  local did_build=0
  if grep -qE '^frontend/' <<<"$changed"; then
    log "  前端有變 → next build"; build_frontend || { log "  next build 失敗"; return 1; }; did_build=1
  fi
  if grep -qE '^(backend|rules|fixtures)/' <<<"$changed"; then
    sudo systemctl restart ntpc-backend
  fi
  [[ $did_build == 1 ]] && sudo systemctl restart ntpc-frontend
  return 0
}

case "${1:-run}" in
  install)
    if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then git init -q -b "$BRANCH"; fi
    git remote get-url origin >/dev/null 2>&1 || git remote add origin "$REPO"
    git remote set-url origin "$REPO"
    mkdir -p ~/.ssh && chmod 700 ~/.ssh
    [[ -f ~/.ssh/id_ed25519 ]] || ssh-keygen -q -t ed25519 -N "" -C "ntpc-autodeploy@ec2" -f ~/.ssh/id_ed25519
    grep -q "github.com" ~/.ssh/known_hosts 2>/dev/null || ssh-keyscan -t ed25519,rsa github.com >> ~/.ssh/known_hosts 2>/dev/null
    sudo tee /etc/systemd/system/ntpc-autodeploy.service >/dev/null <<EOF
[Unit]
Description=ntpc autodeploy: pull ${BRANCH} from GitHub and rebuild if changed
[Service]
Type=oneshot
User=ubuntu
WorkingDirectory=${APP}
Environment=DEPLOY_BRANCH=${BRANCH}
ExecStart=/usr/bin/flock -n /tmp/ntpc-autodeploy.lock /bin/bash -c 'cp ${APP}/deploy/autodeploy.sh /tmp/ntpc-autodeploy.run.sh && exec /bin/bash /tmp/ntpc-autodeploy.run.sh run'
EOF
    sudo tee /etc/systemd/system/ntpc-autodeploy.timer >/dev/null <<EOF
[Unit]
Description=ntpc autodeploy every 60s
[Timer]
OnBootSec=90
OnUnitActiveSec=60
AccuracySec=5
[Install]
WantedBy=timers.target
EOF
    sudo systemctl daemon-reload && sudo systemctl enable --now ntpc-autodeploy.timer >/dev/null
    log "autodeploy 已安裝：每 60 秒檢查 origin/${BRANCH}"
    echo; echo "=== 把下面這行加到 GitHub repo → Settings → Deploy keys（唯讀即可） ==="; cat ~/.ssh/id_ed25519.pub; echo "==="
    ;;
  run)
    if ! git fetch -q origin "$BRANCH" 2>/tmp/ntpc-fetch.err; then log "fetch 失敗（deploy key 還沒加？）：$(tail -1 /tmp/ntpc-fetch.err)"; exit 0; fi
    old="$(git rev-parse --verify -q HEAD 2>/dev/null || true)"; [[ -n "$old" ]] || old=none; new="$(git rev-parse "origin/$BRANCH")"
    [[ "$old" == "$new" ]] && exit 0
    log "更新 ${old:0:7} → ${new:0:7}：$(git log -1 --format=%s "$new")"
    if apply "$old" "$new" && health_ok; then
      log "  完成 ${new:0:7}"
    else
      log "  健康檢查失敗，回滾到 ${old:0:7}"
      if [[ "$old" != none ]]; then apply "$new" "$old" || true; health_ok && log "  回滾完成" || log "  回滾後仍不健康，請人工處理：sudo journalctl -u ntpc-backend -u ntpc-frontend -n 50"; fi
    fi
    ;;
  rebuild)   # 對目前 HEAD 完整重裝依賴、重建前端、重啟（第一次或懷疑不同步時用）
    new="$(git rev-parse HEAD)"; log "完整重建 ${new:0:7}"
    if apply none "$new" && health_ok; then log "  完成 ${new:0:7}"; else log "  重建失敗，請看 journalctl"; exit 1; fi
    ;;
  status)
    echo "commit: $(git rev-parse --short HEAD 2>/dev/null || echo none)  origin/${BRANCH}: $(git rev-parse --short "origin/$BRANCH" 2>/dev/null || echo '?')"
    systemctl is-active ntpc-autodeploy.timer ntpc-backend ntpc-frontend caddy | paste -sd' ' -
    tail -10 "$LOG" 2>/dev/null || true
    ;;
  *) echo "用法：autodeploy.sh install|run|status"; exit 2;;
esac
