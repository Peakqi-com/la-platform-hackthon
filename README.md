# ntpc-appraisal-review

2026 新北市 AI 智慧城市黑客松 · 地政局命題「AI 輔助不動產估價案件審查」。

土地徵收補償市價查估書表（勘查表 → 區域因素分析明細表 → 比較法調查估價表）的自動填寫與審查：
規則引擎讀基準明細表 JSON，從勘查事實推等級、查矩陣得修正率、加總、跨表抄填、算價格鏈；
反向比對估價師填的表，逐條指出不一致並引用作業手冊審查重點與基準表格位。

## 快速開始

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
python3 -m pip install -e ".[dev,llm]"                 # 或 pip install -r requirements.lock 鎖定版本
python3 -m pytest -q                                   # 後端測試（引擎重現範本、審查、空間、市場、API）
python3 -m uvicorn app.main:app --port 8000            # http://localhost:8000/docs
cd ../frontend && npm ci && BACKEND_URL=http://127.0.0.1:8000 npm run build && npx next start -p 3000
```
圖資與資料（data/，不進 git）的建置與部署見 `docs/08_data_prep_and_todo.md` 與 `deploy/runbook_ec2.md`。

## 結構

```
CLAUDE.md          開發指引（先讀）
docs/              01 題目範圍 · 02 領域規則 · 03 schema · 04 架構 · 05 資料來源 · 06 路線圖 · 07 計算法源對照 · 08 資料準備與待辦 · 09 土管要點待核對
rules/             基準明細表 JSON、內政部上限、設施量測方式、建蔽率容積率表、都市地價指數、鄉鎮市區鄰接
fixtures/          範本案例（驗收測試資料）
backend/           FastAPI + 規則引擎（app/engine）+ 空間／市場／報表模組 + 資料建置腳本（scripts/）+ 測試
frontend/          Next.js 16（四步驟：案件總覽 → 輸入資料 → 產出書表 → 審查 → 輸出）
deploy/            EC2 手動部署手冊、docker user-data、Caddyfile、OSRM 說明
```

## 授權與來源

- 命題文件、作業手冊、書表範本、基準明細表由新北市政府地政局提供，僅供本專案使用。
- 底圖與段籍圖：內政部國土測繪中心 WMTS。路網、步行圖、設施點位：© OpenStreetMap contributors，ODbL；`data/poi_ntpc.sqlite` 等為 OSM 衍生資料庫，散布時須保留此標示。
- 都市計畫使用分區（新北市城鄉發展局）、內政部實價登錄、水利署淹水潛勢圖、環境部列管污染源、經濟部商圈清冊、新北市交通局停車格、高公局交流道、內政部都市地價指數：政府資料開放授權條款第 1 版。
- 高程：AWS Terrain Tiles（Mapzen terrarium）。
