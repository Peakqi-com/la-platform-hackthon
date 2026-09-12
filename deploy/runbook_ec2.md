# EC2 部署手冊（不用 docker；Ubuntu 24.04，t3.medium 以上）

目標：30 分鐘內在主辦給的 EC2 跑起後端（8000）與前端（3000）。全部指令在 EC2 上以 ubuntu 使用者執行。

## 競賽規範對照（黑客松競賽環境規範與限制 20260722；部署前逐條勾）
- [ ] 區域用 **us-east-1** 或 us-west-2；EC2 用 Standard 系列（t3.medium／m 系列），一台就夠，不開 GPU、不做模型訓練。
- [ ] Security Group **不可對外全開**：只開 443／80（Caddy），SSH 22 限自己的 IP；8000 不開，前端 3000 只在用 Caddy 反向代理時不開。
- [ ] 不建立公開 S3 Bucket；資料檔若放 S3 用 Block Public Access，EC2 以 IAM role 讀取。
- [ ] 不建立公開存取的 RDS／EMR（本系統不用資料庫）。
- [ ] Bedrock：請求 < 1 RPS（程式已內建節拍器 `BEDROCK_MIN_INTERVAL`，預設 1.1 秒）；只開通 `BEDROCK_MODEL_ID` 用到的模型，賽後撤銷。
- [ ] 不上傳個人資料：案件示範用職稱當操作身分；實價登錄為去識別化開放資料；不放真實估價師姓名。
- [ ] 機密只走環境變數（`.env` 已在 .gitignore），repo 私有；不把 AWS 金鑰寫進任何檔案。
- [ ] 沒用 Kiro，不需 `.kiro`。

## 一鍵版（2026-09-12 起，優先用這個）
`deploy/provision.sh` 把下面第 1–5 步全部自動化：金鑰對 → 安全群組（443／80 對外，22 只給本機 IP）→ IAM role（EC2 直接呼叫 Bedrock，不用金鑰）→ t3.medium Ubuntu 24.04 → 固定 IP → 上傳程式與 data/ → venv、npm build、systemd、Caddy → 預載範例 → 健康檢查。
```bash
brew install awscli                                   # 本機一次；憑證貼 ~/.aws/credentials（INI 格式，不是 export 格式）
aws sts get-caller-identity                           # 確認身分與區域（us-west-2 或 us-east-1）
./deploy/provision.sh                                 # 全部；結束印出 https://<IP>.sslip.io 與 ssh 指令
DATA_TGZ=~/ntpc-data.tgz ./deploy/provision.sh        # 帶資料包；或本機有 data/ 就自動 rsync
./deploy/provision.sh --sync-only                     # 改程式後重新上傳＋重啟（EC2 沿用）
./deploy/teardown.sh                                  # 賽後收攤
```
- 可調：`NAME`、`INSTANCE_TYPE`、`REGION`、`BEDROCK_MODEL_ID`（預設 `us.anthropic.claude-sonnet-4-5-20250929-v1:0`，這個帳號要用 inference profile ID，直接模型 ID 不行；Opus 5／4.7 未開通）、`ANTHROPIC_API_KEY`（有給就改走 anthropic）、`SSH_CIDR`。
- 服務用 systemd（`ntpc-backend`、`ntpc-frontend`、`caddy`），重開機自動起；log：`sudo journalctl -u ntpc-backend -n 50`。程式在 `/opt/app`，環境變數在 `/opt/app/.env`。
- macOS 打包會夾帶 `._*` AppleDouble 檔，`rules/*.json` 的 glob 會把它們當 JSON 讀而 500；provision.sh 已用 `COPYFILE_DISABLE=1` 並排除，remote_setup.sh 解開後也會再清一次。
- 本機 macOS 內建 bash 3.2：腳本裡變數後面緊接中文要寫 `${VAR}`，否則會被當成變數名的一部分。
- 2026-09-12 已在帳號 565762307497（us-west-2）跑過一次：https://54.188.82.141.sslip.io，i-0028c53f20f3ccf9b，私鑰 `~/.ssh/ntpc-key.pem`（本機沒有這把鑰匙且 22 埠只開給佈建時的 IP，從其他機器連不上）。
- 2026-09-13 從外部看到的狀況：`/api/health` 500、`POST …/from_lot` 500（13 秒後）、`/api/reload` 正常但顯示「實價登錄 1970-01-01」＝主機缺 `data/lvr/f_land.json`。自動部署以 `/api/health` 含 `"ok":true` 判斷成功，健康檢查 500 會讓每次部署都回滾、主機停在舊版；已改成每一項各自包起來（壞掉的項目列在 `errors`），依地號產生失敗改回 `{"detail": "依地號產生失敗（例外類型）：原因"}`。補檔：`rsync -e 'ssh -i ~/.ssh/ntpc-key.pem' data/lvr/f_land.json ubuntu@54.188.82.141:/opt/app/data/lvr/`，看原因：`sudo journalctl -u ntpc-backend -n 100`、`/opt/app/deploy/autodeploy.sh status`。

### 自動部署（push 到 main 即上線）
EC2 上 `deploy/autodeploy.sh` 由 systemd timer 每 60 秒 `git fetch`，main 有新 commit 就 `reset --hard`、依變更重裝依賴／重建前端、重啟，健康檢查失敗自動回滾；紀錄在 `/opt/app/deploy.log`。拉取式，不開入站埠、不存 AWS 金鑰。
```bash
ssh -i ~/.ssh/ntpc-key.pem ubuntu@<IP> '/opt/app/deploy/autodeploy.sh install'   # 一次；印出公鑰 → GitHub repo Settings → Deploy keys（唯讀）
ssh -i ~/.ssh/ntpc-key.pem ubuntu@<IP> '/opt/app/deploy/autodeploy.sh status'    # 目前 commit、timer、最近紀錄
```
改監看分支：`Environment=DEPLOY_BRANCH=release` 寫進 `/etc/systemd/system/ntpc-autodeploy.service` 後 `daemon-reload`。

## 0. 本機先準備（賽前）
```bash
cd ntpc-appraisal-review
python3 -m pip freeze > backend/requirements.lock            # 已有一份，環境有變再重做
tar czf ntpc-data.tgz \
  data/zoning/ntpc_zoning.sqlite data/osm/roads.sqlite data/osm/walk.sqlite data/osm/districts.geojson \
  data/poi_ntpc.sqlite data/osm/addresses.sqlite data/lvr/f_land.json data/flood/ntpc_24h350r.geojson \
  data/tiles data/terrain data/cadastre/default.geojson data/cadastre/p002_block_estimate.json \
  data/示範_地價區段圖_金山.geojson data/示範_地籍圖_金山P002-00.geojson data/sources/manual_poi.geojson 2>/dev/null
ls -la ntpc-data.tgz                                          # 約 1.4 GB（門牌庫 1 GB）；PDF 原檔、shp、zip、walk_cache 不用帶
```
private repo 要用 deploy key 或 token clone；或直接 `tar czf ntpc-src.tgz --exclude=node_modules --exclude=.next --exclude=data .` 帶上去。

## 1. 系統套件
```bash
sudo apt-get update && sudo apt-get install -y python3.12 python3.12-venv python3-pip git curl
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash - && sudo apt-get install -y nodejs   # apt 內建 node 18 跑不動 Next 16
node -v   # v22
```

## 2. 程式與資料
```bash
git clone <repo> ntpc-appraisal-review && cd ntpc-appraisal-review     # 或解開 ntpc-src.tgz
tar xzf ~/ntpc-data.tgz                                                  # 展開到 data/
mkdir -p data/cases data/audit data/cadastre/cases
```

## 3. 後端
```bash
cd backend
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements.lock                     # 鎖定版本；失敗再 pip install -e ".[llm]"
pip install -e ".[llm]"
export ANTHROPIC_API_KEY=...                         # 選用；沒有也能跑
nohup .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > ../backend.log 2>&1 &
curl -s http://127.0.0.1:8000/api/health | head -c 300   # 看 roads/walk_graph 是 sqlite、poi count > 90000、lvr 有筆數
```

## 4. 前端（先起後端再 build，BACKEND_URL 在 build 時寫死）
```bash
cd ../frontend
npm ci
BACKEND_URL=http://127.0.0.1:8000 npm run build
nohup npx next start -p 3000 -H 0.0.0.0 > ../frontend.log 2>&1 &
```
Security Group 只開 443／80（用 deploy/Caddyfile 反向代理到 3000）；8000 與 3000 不對外。沒有 Caddy 時才暫開 3000，且不可整個 Security Group 對外全開（規範第 3 點）。

## 5. 上線前 5 分鐘
```bash
cd ..
for v in template tampered residential blank_survey; do curl -s "http://127.0.0.1:8000/api/cases/demo?variant=$v&save=true" > /dev/null; done   # 預載四個範例
cd backend && .venv/bin/python scripts/prefetch_tiles.py --bbox <minlon,minlat,maxlon,maxlat>                 # 主辦指定地區的底圖（會場沒外網才需要）
.venv/bin/python -c "from app.spatial import terrain; print(terrain.prefetch((minlon,minlat,maxlon,maxlat)))"  # 同上，高程
```
.venv/bin/python scripts/prebuild_walk.py                                                                    # 預建 29 區步行圖快取（2 分鐘），量測不必等建圖
主辦給的地籍圖（GeoJSON，屬性 段名／地號）放 `data/cadastre/default.geojson`，一鍵建案的地號下拉才會有該區地號。

## 6. 常見問題
- 首頁狀態列「設施資料庫 0 筆」：`data/poi_ntpc.sqlite` 沒放到位，或 `POI_DB` 指錯。
- 地圖空白：`data/tiles` 沒帶且 EC2 出不了網（wmts.nlsc.gov.tw）。
- 前端打 API 404：build 時 BACKEND_URL 不對，改好重新 `npm run build`。
- 記憶體：後端啟動約 1.5 GB（實價登錄＋設施庫），t3.small 會 OOM。
- 重啟：`pkill -f "uvicorn app.main"`、`pkill -f "next start"` 後重跑第 3、4 步的啟動指令。
