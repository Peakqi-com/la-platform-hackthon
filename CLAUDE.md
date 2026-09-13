# AI 輔助不動產估價案件審查 — 開發指引

2026 新北市 AI 智慧城市黑客松，地政局命題。決賽 9/12–13，30 小時現場實作 + Live Demo，
**必須部署到當天才給的 AWS 帳號，並交出一個委員可以現場操作的網址。**
賽前要把程式全部寫完，當天只做部署與測試。

## 版本控制

GitHub 私有 repo `Peakqi-com/LA-platform`（Land Administration platform），主分支 `main`，節點打標籤（`v0.1-ui-formal` 正式版介面、`v0.2-p0-ux` P0 UX、`v0.3-p1-ux` P1 UX：案件狀態／承辦裁決／長表單工具／並排比較標的／抽取信心／上傳先預覽、`v0.4-p2` P2：操作身分與紀錄／圖說 PNG／法源提示／列印）。`data/` 不進 git，重建方式見 `data/README.md` 與 docs/05、docs/08。

## 一句話

把土地徵收補償市價查估的「勘查表事實 → 優劣等級 → 修正率 → 加總 → 跨表抄填」這條鏈自動化，
並反向做審查：比對估價師填的表和規則算出的表，逐條指出不一致並引用依據。

## 先讀什麼

1. `docs/01_problem_and_scope.md` — 題目、MVP 範圍、深/中/淺三種情境、demo 腳本
2. `docs/02_domain_rules.md` — 作業手冊裡真正需要的規則（審查重點、距離量測、計算式、尾數）
3. `docs/03_data_schema.md` — 內部 schema，所有模組只認這個
4. `docs/04_architecture.md` — 服務切分、API、部署
5. `docs/05_data_sources.md` — 資料來源總表（法規、範本、政府開放資料、OSM、圖磚、地籍、路徑、語言模型、字型；標離線／線上／需申請／推定／備援）
6. `docs/06_roadmap.md` — 到決賽前的順序
7. `docs/07_calculation_basis.md` — **每條算式的法源對照**（辦法條號／手冊頁碼／程式位置／手冊算例驗證）
8. `docs/08_data_prep_and_todo.md` — 資料準備操作指南、替代方案評估、待人處理清單
7. 原始文件在 `docs/reference/`（命題、手冊 PDF 與全文擷取、書表範本、基準明細表）

## 不可違反的原則

- **規則引擎是確定性的，不用 LLM。** 每一個等級和修正率都要能指回 `rules/*.json` 的某一格。LLM 只做文件抽取和審查意見文字。
- **計算不是湊範本數字，是照法規算。** 每一條算式都要能指回查估辦法條號或作業手冊頁碼，寫在 `docs/07_calculation_basis.md`；手冊 p.100–102 的官方算例是第二組驗收（`tests/test_manual_examples.py`）。範本與手冊不一致時以手冊／辦法為準並標疑點。
- **`backend/tests/test_acceptance.py` 永遠必須通過。** 它用地政局的範本驗收：表 5-2 每個等級、表 4 每個差異率、13.00%、212,958。改規則或引擎前先跑它。
- **基準表不能寫死。** 當天的案子可能不在金山、不是商業用地。`rules/` 是資料，引擎讀 JSON；新基準表 = 新 JSON，不改程式。
- **每筆距離都要帶來源與量測方式**（直線/步行、資料集名稱、起點約定）。這是長官點名的要求，也是 UI 上必須看得到的東西。
- **推定的規則要標成「需人工確認」，不要硬判錯。** 例：特殊設施多個時取最不利者（範本推定）、區域因素距離從區段邊界量（推定）、金山表道路種類 max 8 超過內政部上限 5（範本本身疑點）。
- **input adapter 與部署腳本是隔離不確定性的兩個模組。** 當天資料格式不明 → 只改 adapter；帳號權限不明 → 只改 deploy。其他模組不動。
- **不依賴外部 API 做 demo。** POI、分區、地價區段、OSRM 全部事先下載進 `data/`，當天只有底圖 tile 是線上拉。

## 技術棧

- 後端 `backend/`：Python 3.12、FastAPI、shapely/pyproj/pyshp、openpyxl、pymupdf（`fitz`）、reportlab、python-docx、pillow。規則引擎在 `app/engine/`；空間 `app/spatial/`（全區圖資 SQLite 依案件 bbox 局部載入）、市場 `app/market/`、報表 `app/report/`。
- 前端 `frontend/`：Next.js（`output: 'standalone'`）、Leaflet + 國土測繪中心 WMTS。**不用 Supabase、不用 localStorage 持久化**，資料在後端。
- 路徑：OSRM foot profile 容器（`deploy/osrm.md`）。備選 AWS Location Service。
- LLM：`LLM_PROVIDER=anthropic|bedrock|mock` 切換，介面在 `app/llm/`（`base.py` 定 `complete(prompt, images, system)`；`anthropic_provider.py` 走官方 SDK、`bedrock_provider.py` 走 boto3 Converse、`mock_provider.py` 測試用）。只用在 PDF vision 抽取與意見書文字。
- 部署：正式用 `deploy/runbook_ec2.md`（不用 docker）；docker compose 為備用。HTTPS 靠 Caddy + sslip.io（`deploy/`）。

## 常用指令

```bash
cd backend && python3 -m pip install -e ".[dev,llm]"   # 這台機器沒有 pip 指令，用 python3 -m pip；資料建置腳本另裝 ".[scripts]"
python3 -m pytest -q                        # 驗收 + 手冊算例 + adapter + 輸出 + API 測試
python cli.py ../fixtures/sample_case_P002-00.json   # 印出表5/表4
python -m app.adapters.rules_table ../docs/reference/評價基準明細表範例.pdf --csv out.csv --json outdir --prefix xxx   # 基準表 PDF → CSV / rules JSON
uvicorn app.main:app --reload               # API 在 :8000，/docs 有 swagger
docker compose up --build                   # 全套
```

## 模組現況速查（第 3 步完成後）

- `app/adapters/common.py`：`AdapterResult{data, missing_fields, warnings, confidence}`、值正規化、表格版面偵測（表7 轉置 / 一列一筆）。「-」= 明示免填 → None 不列 missing；空白 → None 且列 missing。
- `app/adapters/excel_parcels.py` / `excel_comparables.py`：表7 清冊、買賣實例 → Parcel[] / Comparable[]；各附 writer 供 round-trip 與反向產表。
- `app/adapters/rules_table.py`：基準明細表 PDF / canonical CSV（`fixtures/jinshan_commercial_rules_table.csv` 是格式範例）→ rules JSON。細項名稱對回內政部項目目錄（`REGIONAL_CATALOG` / `INDIVIDUAL_CATALOG`），備註欄條件文字用文法解析；對 `moi_max_ranges.json` 檢查上限只 warning。
- `app/adapters/pdf_forms.py` + `pdf_forms_vision.py`：書表 PDF → sections / parcels / comparables / submitted。文字層優先（範本還原 99%），掃描件走 vision；信心值 < 0.6 → missing、0.6–0.85 → warning。從表單抄來的距離 measure/origin 依 `facility_measurement.json` 帶預設並標 `assumed: true`。
- `app/output/xlsx.py` + `xlsx_table1.py`：表1 / 表5 / 表4 Excel，版面照範本；寫值不寫公式；百分比以百分點存（5.0）配 `0.00"%"` 格式；免修正「-」；布林細項顯示「無／有」；表1 等級數字欄由規則引擎判或用估價師填值。
- `app/engine/tables.py` 價格鏈拆成純函式（`date_adjusted_price`、`trial_price`、`abs_sum`、`default_similarity_and_weights`、`comparison_price`、`round_land_price`、`parcel_market_price`），每個都註法源；`Table4.subject_land_price` = 比較價格依辦法 §21 進位。`verify_comparables` 檢查 §17 蒐集期間、§19 件數、期日調整率與指數比、§13 單價。
- `app/spatial/`：`geo`（TWD97 投影、直線距離、區段邊界最近點）、`poi`（GeoJSON/SQLite/CSV POI 庫）、`osrm`（foot 路徑；失敗退 `straight_estimated` ×1.3）、`distance`（單筆 → Facility 帶 measure/origin/source/佐證）、`reference`（案件層級參照設施、`fill_parcel` / `fill_section`）、`service`（單例、`fill_case`）。`scripts/build_poi.py` 建 POI 庫（manifest 或 Overpass）；`scripts/check_jinshan_realdata.py` 用真實 OSM 資料對範本距離。
- `app/spatial/cadastre.py`：地籍幾何三來源 — 地籍圖檔 `FileCadastreProvider`（GeoJSON/Shapefile，`CADASTRE_GEOJSON`）→ NLSC 地籍查詢 API（CAD_004，**需申請**，`NLSC_API_KEY`，介面留空）→ 人工質心＋清冊面積寬深合成（`synthetic`）。段代碼用 NLSC 開放 API 快取（金山區 F25、金美段 1027、溫泉段 1026）。
- `app/spatial/bootstrap.py`：`block_from_roads`（路網街廓，補 OSM 缺口、1 cm 網格 noding）、`section_from_roads`（指定路名圍面）、`describe_range`（四至草稿）、`propose_sections`（徵收範圔 × 使用分區 → 區段草稿，status=draft）。
- `app/maps/`：`zoning.py`（新北市使用分區 GeoJSON，欄位 ZONE，只有「商業區」沒有第X種 → 只能當建議）、`layers.py`（sections/parcels/facilities/distance_lines/zoning/roads 六個 GeoJSON 圖層）、`static/viewer.html`（Leaflet + 國土測繪 WMTS，三張圖切換，`GET /maps`）。
- `app/spatial/walking.py`：內建 OSM 步行圖（Dijkstra），OSRM 沒有時的路徑距離；順序 OSRM → 內建圖 → 直線×1.3，`provenance.router` 記來源。資料 `data/walk_graph_jinshan.geojson`（`WALK_GRAPH_GEOJSON`）。
- 人工標定 POI：`POST /api/spatial/poi` → `data/sources/manual_poi.geojson`（來源「人工標定」，啟動時自動併入 POI 庫）。政府資料 manifest：`data/sources/manifest.json`（已含中油加油站 1,972 筆），操作見 `docs/08_data_prep_and_todo.md`。
- `app/report/opinion.py`：審查意見書。findings → 逐條意見（每句 `[F-xxx]` + 法源）→ Markdown；`polish_items` 用 LLM 潤稿但守門（標籤齊、沒有新數字），失敗退回模板句；沒 LLM 也能出。`POST /api/report`。
- `app/cases.py` + `/api/cases*`：案件存後端（記憶體 + data/cases/*.json）；`/api/cases/demo?variant=template|tampered|residential&save=true` 三個 demo 變體（竄改版錯四處；住宅版用 `rules/demo_residential_*.json`，標示為示範非官方）。`/api/rules`（摘要）、`/api/rules/{id}`（含全矩陣）、`/api/rules/import`。
- `app/main.py`：`/api/adapt`、`/api/export/xlsx`、`/api/spatial/{status,distances,fill,poi}`、`/api/cases*`、`/api/cadastre/{resolve,sections}`、`/api/bootstrap/{block,sections,sections_by_land_value}`、`/api/maps/layers`、`GET /maps`、`/api/report`。
- `frontend/`：Next.js 16，側邊欄依流程分段（① 輸入：基本資料／宗地與實例／基準表 → ② 產出書表：勘查表／表5／表4 → ③ 審查 → ④ 輸出），頁首標「這一頁的輸入／產出／下一步」，書表用法定全名；名稱對照來自 `GET /api/meta`。**勘查表（表1）是產出**：`app/spatial/survey_draft.py` + `POST /api/spatial/survey_draft` 依分區圖／路網／設施資料庫推算，推不出的欄位列「需人工填載」；demo 變體 `blank_survey`。`/api/*` 由 rewrites 代理到 `BACKEND_URL`；本機用生產版驗收（README 已知問題）。
- 資料（都不進 git，見 `data/README.md`）：`data/poi_osm_jinshan.sqlite`（OSM POI 340 筆，面狀設施帶多邊形）、`data/roads_osm_jinshan.geojson`（294 段）、`data/zoning/jinshan_zoning.geojson`（城鄉局分區 399 筆）、`data/cadastre/p002_block_estimate.json`。demo 幾何估計在 `fixtures/sample_geometry_P002-00.json`（進 git，來源標「估計」）。
- `data/poi_osm_jinshan.sqlite`（不進 git）：金山區 OSM POI 349 筆，重建：`python scripts/build_poi.py --overpass "25.20,121.60,25.26,121.68" --out ../data/poi_osm_jinshan.sqlite`；啟動時 `POI_DB` 指向它。

## 現況（依 docs/06_roadmap.md 更新）

- [x] 金山商業用地區域/個別基準表 → `rules/*.json`
- [x] 內政部最大影響範圍 → `rules/moi_max_ranges.json`
- [x] 設施 → 量測方式設定 → `rules/facility_measurement.json`
- [x] 規則引擎：等級判定、矩陣、表5、表4、價格鏈、審查比對（7 個測試通過）
- [x] FastAPI 骨架 `/api/run` `/api/verify`
- [x] input adapter：Excel 清冊/實例（雙版面 + round-trip）、基準表 PDF/CSV → rules JSON（金山表反向驗證等價）、書表 PDF（文字層 99% + vision 備援）
- [x] LLM provider 介面 `app/llm/`（anthropic / bedrock / mock，環境變數切換）
- [x] 輸出：表1 / 表5 / 表4 Excel（照範本格式）
- [x] API：`/api/adapt`、`/api/export/xlsx`、`/api/spatial/*`
- [x] 計算法源對照 `docs/07_calculation_basis.md` + 手冊 p.100–102 算例測試；§21 尾數、§17 蒐集期間檢查
- [x] 空間模組核心：POI 庫、距離（直線/步行+退回）、參照設施選定、區段邊界起點、`/api/spatial/*`（合成金山座標測試重現範本全部等級）
- [x] 地籍幾何模組（地籍圖檔／NLSC API 介面／質心合成）＋ `/api/cadastre/*`；**NLSC 地籍 API 要申請，地籍圖檔要需用土地人給**
- [x] 區段 bootstrap（路網街廓 + 四至草稿 + 分區切分）＋ 三張圖圖層與 `/maps` 檢視頁；金山 P002-00 能用 OSM 路網圍出、四至草稿三邊與範本一致
- [x] 內建步行圖（OSRM 備援）；真實資料：比準地到學校/市場/公園/站牌步行 114/89/201/168 m，與範本同級距
- [x] 公告現值同值相鄰宗地 → 區段草稿（地價區段圖替代）；新北 113 年公告現值金山 25,244 筆已下載
- [x] 審查意見書（模板句 + 法源 + LLM 潤稿守門）`/api/report`
- [ ] 待人處理清單見 `docs/08_data_prep_and_todo.md` A 節：地籍圖／NLSC API、疑點 B、人工標定三個設施、TDX、AWS；OSRM 改在 EC2 跑
- [x] 審查意見書（LLM 產文字，findings 為依據）
- [x] 前端 UI（Next.js 16，六頁對應 demo 五步；生產版驗過，dev 模式 hydration 問題見 frontend/README）
- [x] UX P0/P1：案件狀態（草稿／審查中／已完成，`PATCH /api/cases/{id}`）、承辦裁決（接受／維持不符＋說明，寫進意見書 `opinion.DECISION_LABEL`）、案件搜尋／排序／複製、長表單摺疊／篩選／方向鍵／未儲存提醒（`components/FormTools.tsx`）、表5／表4 比較標的並排、抽取信心值（<0.85 標黃 `lib/api.ts confidenceFor`）、上傳先預覽再「建立案件並開始審查」
- 用詞：「需人工確認」＝系統判定不足（黃）；「需人工填載」＝欄位空白（紅）；「承辦裁決」＝審查人對不符項的處置
- [x] P2：操作身分（header `X-Actor-Name`/`X-Actor-Role`）與操作紀錄 `app/audit.py`（`data/audit/*.jsonl`，`GET /api/cases/{id}/audit`）；圖說 PNG `app/maps/render.py`（PIL＋NLSC 底圖，`GET /api/cases/{id}/map.png`，Excel「圖說」工作表、意見書第四節、表5 頁小地圖）；法源提示 `app/report/basis.py` → `/api/meta.legal_basis` → `components/Basis.tsx`；列印樣式與字級；dev 模式改用 3001 埠（見 frontend/README）
- [x] 完整版第 1 段（v0.5-stage1）：案件列（輸入最後修改／產出最後產生、產出已過期）、`POST /api/cases/{id}/generate`（記輸入指紋＋摘要，裁決對不到就標 stale）、`reset_preview`／`reset`（回原始快照 `original`、清裁決與產出、狀態回草稿）、另存為新案件；輸入頁的儲存鍵一律「儲存並重新產生書表」；過期時產出／輸出頁淡化且停用下載；圖說頁工具列改兩層（工具選單＋下載 PNG）
- [x] 完整版第 2 段（v0.6-stage2）：書表預覽 `/sheets` 六頁照《查估書表範本》頁序；格線來源 `app/output/grid.py`（openpyxl 工作表 → 格子 JSON → 前端 HTML／reportlab PDF，Excel、預覽、PDF 同一份版面）；`GET /api/cases/{id}/sheets`、`sheets.pdf`、`sheets.xlsx`（六張工作表：三表＋三圖）；圖說加範本元素（標題「{區}土地徵收市價查估地價區段略圖」、標準比例尺 1:1800…、不動產估價師欄、實例編號、徵收地）；PDF 中文字型 `app/fonts/wqy-microhei.ttc`（TTC，reportlab subfontIndex），EC2 也可用系統 wqy／Noto TTC
- [x] 完整版第 3 段（v0.7-stage3）：側邊欄五項（案件總覽／①輸入資料／②產出書表／③審查／④輸出，勾號＝該段完成）；①輸入資料 `/input?tab=case|parcels|rules` 分頁（舊路徑 /case /parcels /rules 仍可用）；②＝`/sheets` 六頁預覽，審查對照檢視（/table1、/tables）從預覽頁進；拿掉每頁四格流程列，頁首說明縮一句＋「更多說明」，圖例預設收起；開啟案件直接到 ②；一頁一主鍵（儲存並重新產生書表／下載完整書表 PDF／儲存裁決／下載全部 zip）；`GET /api/cases/{id}/bundle.zip`
- [x] 匯入／匯出標示（`components/IO.tsx`）：欄位旁 ⬆⬇ 小標、卡片「可匯入／可匯出」徽章、下載鍵一律 ⬇；宗地與實例分頁可直接匯入清冊／實例 xlsx（`POST /api/cases/{id}/import`，依地號併入、只覆蓋有值欄位、對不到的回報）並匯出（`parcels.xlsx`／`comparables.xlsx`，填好可再匯入）；基準表列表可匯出 JSON
- [x] 重複功能清理三批：刪首頁目前案件卡／列表複製／對照檢視下載 Excel／審查頁下載意見書與試用鍵／PNG 連結／案件 JSON／說明卡／即時核算卡；估價師簽章與填寫日期存 `case.appraiser`／`case.fill_date` 全輸出共用；意見書落款用側邊欄身分；狀態切換在案件列；地圖工具（推估區段、設定比準地、重新量測、人工標定）全在 ① 基本資料分頁，`/map` 只剩互動檢視歸 ②；列印鍵只在書表預覽、審查、意見書、對照檢視
- [x] 案件總覽改為承辦／主管儀表：KPI（全部、審查中、待處理不符項、產出已過期、已完成）、審查案件上傳區、從零建案表單（`POST /api/cases/new`，依用地別 `pick_rulesets`）、案件清單（審查結果、比較價格、產出狀態、最後操作、依狀態的「下一步」）；`list_cases()` 多 n_error／n_warn／n_accepted／comparison_price／last_action
- [x] 會場風險：底圖改走後端代理 `GET /api/tiles/{z}/{x}/{y}`（互動地圖與 PNG 共用 `data/tiles` 快取），`python3 scripts/prefetch_tiles.py` 預抓金山一帶 z14–18（1,356 塊）；首頁顯示語言模型／底圖快取／設施庫狀態；掃描件無金鑰時給明確訊息；刪除改「封存」（`POST /api/cases/{id}/archive?undo=`，清單勾「已封存」可復原），DELETE 端點保留但介面不用
- [x] 段籍圖與地籍圖：瓦片代理多 `layer=LANDSECT`（段籍圖，略圖與區段圖 PNG／互動地圖疊上，`prefetch_tiles.py` 一併預抓）；`POST /api/cases/{id}/cadastre` 匯入需用土地人地籍圖（GeoJSON 或 Shapefile zip，預設 TWD97；自動找段名／地號欄，8 碼地號可讀），存到 `data/cadastre/cases/<id>.geojson` 並記在 `case.cadastre`，用真實界線補比準地／比較標的幾何；圖層多 `cadastre`（界線＋地號，PNG 在 1:3000 以內標地號）；示範檔 `data/示範_地籍圖_金山P002-00.geojson`（合成，非真地籍）
- [x] 地價區段圖匯入 `POST /api/cases/{id}/sections_map`（GeoJSON/KML/GML/SHP zip，依區段編號對本案區段，來源 `section_map`＝正式範圍；整份存 `data/cadastre/cases/<id>_sections.geojson`，圖層 `section_map` 畫鄰近區段虛線＋編號）；基本資料分頁主列＝匯入區段圖／匯入地籍圖／重新量測，點圖推估與人工標定收進「替代方式」摺疊；介面文字不出現主辦、比賽等字樣
- [x] 審查意見書改出 Word／PDF（`app/report/render.py`，python-docx＋reportlab，附三張圖說）：`GET /api/cases/{id}/report.docx|.pdf?reviewer=&reviewer_role=`；zip 內含兩種；不再提供 .md 下載（`/api/report` 的 markdown 只做頁面預覽）。依賴：reportlab、python-docx、pyshp、certifi 已寫進 pyproject
- [x] 一個案件、多份輸入檔（`app/inputs.py` 純函式合併＋`main.py` 端點）：`POST /api/cases/from_inputs`（多檔建一案；沒書表 PDF 要給案號與基準日）、`POST /api/cases/{id}/inputs`（多檔加入既有案）、`DELETE /api/cases/{id}/inputs/{iid}`（移除＝回 `inputs_base` 快照重新併入其餘檔）、`GET …/inputs/{iid}/file`；併入順序 書表 → 基準表 → 清冊 → 實例 → 地籍圖 → 區段圖；書表拆檔（勘查表／表5／表4 各一份）併入結果與整份相同（`tests/test_inputs.py`）；`/api/adapt` 結果依 sha1 快取 30 分鐘，首頁預覽後建案不重跑影像辨識；單檔 `…/import` 改走同一流程。前端：新增案件對話框「上傳輸入檔」多選→逐份預覽→「合併為一個案件／每份各建一案／加入到既有案件」；案件清單「輸入資料」徽章欄（`components/Inputs.tsx` `InputBadges`）、案件列「輸入檔 N 份」、①基本資料分頁「輸入檔」卡片（加入／移除／下載原檔）、審查頁「輸入檔不一致」表。操作紀錄動作 `input`／`input_remove`
- 圖說底圖抓 NLSC WMTS 需要網路與憑證（python.org 版 Python 用 certifi）；瓦片快取在 `data/tiles/`；離線時白底並註明
- [x] 2026-09-12 書表頁數依區段數：勘查表每個區段一張（比準地區段在前、比較標的區段依序），再表5、表4、三張圖說；Excel 一表一工作表、預覽與 PDF 同序。決賽題目四個區段 → 9 頁。地政局正式範本另有 `app/output/official_xlsx.py`（docs/12）。
- [x] 2026-09-13 首頁（城市起風）五章故事之後接「系統功能」九段（資料前提 → 一條鏈 → 三個入口 → 距離出處 → 規則引擎 → 逐格審查 → 樹林實案 → 輸出部署 → 綜上所述＋未來應用），頁尾放出題／主辦／協辦單位；檔案在 `frontend/public/city-wind/features/` 與 `features*.css`，說明見 docs/15 第五批。新增檔案後要重新 `npm run build`。頁尾六個 logo 由 `frontend/scripts/make_logos.py` 從根目錄 `Logo/`（原始檔，不進 git）產生到 `city-wind/logos/`：去背、字轉白、彩色部分保留原色
- [ ] demo 案例 ×3、runbook、影片、簡報
