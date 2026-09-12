# 04 架構

## 服務切分（docker compose，本機 = EC2）

```
frontend (Next.js standalone :3000)
   │  REST
backend (FastAPI :8000)
   ├─ app/adapters/     input adapter：Excel/CSV/PDF/GeoJSON → 內部 schema     ← 當天唯一會改的地方
   ├─ app/engine/       規則引擎：rules.py / tables.py / verify.py            ← 確定性，不碰 LLM
   ├─ app/spatial/      POI 庫、距離（直線/步行）、參照設施、區段 bootstrap
   ├─ app/output/       表1/表5/表4 Excel（openpyxl 套範本）、findings → 審查意見書
   ├─ app/llm/          provider 介面：anthropic | bedrock；用於 PDF 抽取與意見書文字
   └─ app/maps/         三張圖的資料端：分區 GeoJSON、區段多邊形、標註點
osrm (:5000)            台灣 foot profile，離線
caddy (:80/:443)        當天才啟用，sslip.io 自動 HTTPS
data/ (volume, ro)      POI SQLite、分區 GeoJSON、地價區段、OSRM 產物   ← 不進 git，賽前打包
```

## 為什麼後端用 Python 而不是全 Next.js

空間運算（shapely/pyproj/geopandas）、Excel 套版（openpyxl）、PDF 表格（pdfplumber）三塊在 Python 生態系成熟得多；
規則引擎本身兩邊都行。前端維持 Next.js。OSRM 本來就是獨立容器。

## API

| 方法 | 路徑 | 用途 |
|---|---|---|
| GET | /api/health | 存活 |
| GET | /api/rules | 載入的基準表（前端畫判定條件、矩陣） |
| POST | /api/run | 生成：Case → Table5 + Table4 |
| POST | /api/verify | 審查：Case + Submitted → Findings + computed |
| POST | /api/adapt | multipart `file` + `kind`(auto/parcels/comparables/rules_table/pdf_forms) + `land_use` + `use_vision` → AdapterResult（缺欄位清單讓 UI 補） |
| GET | /api/spatial/status | POI 庫筆數/類型、OSRM 狀態 |
| POST | /api/spatial/distances | origin(GeoJSON) + types[] (+section) → 各類最近 k 筆 Facility（含 measure/origin/source/佐證） |
| POST | /api/spatial/fill | 有 geometry 的 Case → 自動填比準地/比較標的/區段的設施距離（案件層級同一參照設施）+ provenance + warnings |
| POST | /api/bootstrap/block | 點位（＋區段內參考點）→ 路網街廓多邊形 + 四至草稿 + 分區建議 |
| POST | /api/bootstrap/sections | 徵收範圍或宗地幾何 × 使用分區 → 區段草稿清單（status=draft） |
| POST | /api/cadastre/resolve | Case + 人工質心 → 補比準地/比較標的幾何（地籍圖檔 → NLSC API → 合成），每筆標來源 |
| GET | /api/cadastre/sections | NLSC 開放 API 段代碼（快取） |
| POST | /api/maps/layers | Case → 六個 GeoJSON 圖層（三張圖共用） |
| GET | /maps | Leaflet 檢視頁（略圖／分區圖／區段圖切換，載 /api/cases/demo） |
| POST | /api/export/xlsx | Case JSON + `meta`(估價師/填寫日期/備註) → 表5+表4 範本格式 Excel（後端跑引擎） |
| POST | /api/report | Case + submitted → findings → 意見書（逐條 [F-xxx]+法源，Markdown；`polish=true` LLM 潤稿含守門） |
| POST | /api/spatial/poi | 人工標定設施 → manual_poi.geojson |
| POST | /api/bootstrap/sections_by_land_value | 同公告現值相鄰宗地 → 區段草稿 |
| GET | /api/cases/demo | 範本案例 + 幾何估計（fixtures/sample_geometry_P002-00.json） |

## 空間模組設計

**POI 庫**：一張 SQLite（+ spatialite 或直接 shapely 掃描，資料量小）表 `poi(type, name, lon, lat, geom, source, attrs)`，
type 用 `rules/facility_measurement.json` 的 key。賽前用 `scripts/build_poi.py` 從各政府資料集轉入。

**距離**：
- straight：pyproj 轉 EPSG:3826 後歐氏距離；面狀設施用多邊形最近點
- walking：OSRM `/route/v1/foot/`，起終點先 `/nearest` snap；失敗（無路網）退回 straight × 1.3 並標 `measure: "straight_estimated"`
- origin：個別因素預設宗地質心（可切臨路邊界中點）；區域因素預設區段邊界最近點（可切比準地）

**參照設施（手冊 p.24 8(2)）**：案件層級 `reference_facilities[type] = 最近者`，全案宗地共用；UI 可改參照點，改了全案重算。

**區段 bootstrap（深模式）**：載入該區公告現值地價區段 shapefile，取與徵收範圍相交者，依用地別（分區 GeoJSON）切分/合併，
產出 `Section.geometry` 與 `range_desc` 草稿（用路名描述四至：以區段多邊形各邊最近的道路名組成）。這一步標「草稿，需估價師確認」。

## 三張圖

Leaflet；底圖國土測繪中心 WMTS `EMAP`（電子地圖）+ `LANDSECT`（段籍）；疊 分區 GeoJSON（顏色照範本圖例）、區段多邊形、比準地/比較標的/設施標註。
輸出：前端 canvas 截圖 PNG 放進 Excel/報告即可，不做印刷級製圖。

## LLM 用在哪（且只在這裡）

1. PDF/掃描書表 → Submitted JSON（vision 抽取，附信心值；低信心欄位 UI 標黃）
2. Findings → 審查意見書自然語言（模板 + LLM 潤稿；每句都要能對回 finding）
3. 備註欄理由合理性摘要（例：§17-3 放寬期間的說明是否完整）——只給提示，不判對錯

Provider 介面：`app/llm/base.py` 定 `complete(prompt, images=(), system=None)` 與 `complete_json()`；`anthropic_provider.py`（官方 SDK，預設 `claude-opus-5`）、`bedrock_provider.py`（boto3 `bedrock-runtime` Converse API）、`mock_provider.py`（測試）；`LLM_PROVIDER` 環境變數切換，`get_provider()` 取得。檔名加 `_provider` 後綴避免與 `anthropic` 套件同名。
Bedrock 模型 ID 當天依開通結果填 `BEDROCK_MODEL_ID`；沒 key 時 import/建構不會炸，呼叫時才丟 `LLMNotConfigured`，pdf_forms 會退回「請人工輸入」。

## 前端頁面（已實作於 frontend/，對應 demo 五步見 frontend/README.md）

1. 案件總覽：載入 demo / 上傳 / 新建
2. 勘查表（表1）：事實表單，距離欄位帶「來源 / 量測方式」標籤與地圖按鈕
3. 表5 / 表4：引擎輸出，可點格子看判定依據（基準表格位高亮）
4. 審查：上傳估價師表 → findings 清單（severity / 條號 / 依據），可匯出意見書
5. 地圖：三張圖切換
6. 設定：基準表選擇/上傳、設施量測方式覆寫

## 部署（EC2 + compose）

賽前：Docker 化全套、`deploy/ec2-userdata.sh` 寫好、`data/` 打包上傳到 S3 或 GitHub release。
當天：開 t3.medium Ubuntu 24.04 → SG 開 22/80/443 → Elastic IP → 貼 user-data → 等 → `https://<ip>.sslip.io`。
備選：App Runner（要 ECR、要更多權限）；再備選：自己的機器跑、只有 Bedrock 呼叫在 AWS（規則上不符，最後手段）。
runbook 見 `deploy/RUNBOOK.md`（待寫，做過一次後照實記）。

## 防呆（委員會亂點）

- 每個輸入欄位有型別與範圍檢查，錯誤訊息用中文說明
- LLM 呼叫每案上限、逾時 30s 退回「無法抽取，請人工輸入」
- 預載 3 個案例，任何頁面都能一鍵回到 demo 狀態
- 後端記每次 /api/* 呼叫（時間、案號、findings 數），賽後看委員試了什麼
