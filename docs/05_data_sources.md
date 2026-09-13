# 05 資料來源總表（2026-09-13）

原則：除底圖圖磚、地籍開放查詢與高程外，資料全部賽前下載進 `data/`（不進 git）或 `rules/`，會場不打外部 API。
每筆設施、距離、幾何都帶來源字串（`source`／`geometry_source`／`provenance`），直接印在書表「來源」欄與介面上。

狀態記號：**離線** 已落地；**線上** 執行時向外取；**需申請** 金鑰或授權尚未取得；**推定** 由替代資料推算，系統標「需人工確認」；**備援** 主要來源失敗才用。
同一份內容的網頁版（可依狀態篩選）：https://claude.ai/code/artifact/db4f7dac-2f05-4928-847d-10b02138685d

## 一、法規與法源

純文字依據。每條算式都能指回辦法條號或手冊頁碼，對照表在 `docs/07_calculation_basis.md` 與 `app/report/basis.py`。

| 名稱 | 系統用途 | 狀態 | 位置 |
|---|---|---|---|
| 土地徵收補償市價查估辦法 §5、7、9、10、13、17–21 | 價格鏈每一步、實例蒐集期間、比較標的件數、地價尾數、行政條件 | 離線 | 手冊 p.115–123；`docs/reference/作業手冊_全文擷取.txt` |
| 土地徵收補償市價查估作業手冊（內政部 104 年 3 月版，169 頁） | 審查重點 iii–x、距離量測標準、明細表訂定原則；p.100–102 官方算例當第二組驗收（`tests/test_manual_examples.py`） | 離線 | `docs/reference/土地徵收補償市價查估作業手冊.pdf`；摘要 `docs/02_domain_rules.md` |
| 內政部最大影響範圍（手冊附件 24、25，p.149–154） | 基準表級距上限檢查，超過只警告 | 離線 | `rules/moi_max_ranges.json` |
| 不動產估價技術規則 §27、32、40-1、41、43、47、54、56、65–67、98 | 權重與相近程度、建物成本間接法、耐用年數、殘價率 | 離線 | `docs/reference/法規依據/` |
| 都市計畫法新北市施行細則 附表一、附表三 | 分區與公共設施用地法定建蔽率、容積率預設 | 離線 | `rules/zoning_bcr_far.json` |
| 各都市計畫區土地使用分區管制要點（新北市 49 個計畫區計畫書） | 各計畫區建蔽率、容積率，優先於施行細則；標 check 者需人工核對（`docs/09_zoning_check_list.md`） | 線上抓取後離線 | 城鄉發展局計畫書網頁 `https://www.planning.ntpc.gov.tw/home.jsp?id=0c69de209c17e5c4`（`scripts/fetch_ntpc_zoning_rules.py`）→ `data/zoning_rules/` → `merge_zoning_rules.py` 併入 `rules/zoning_bcr_far.json` |
| 估價師公會全聯會第四號公報（113.12.11 版） | 含建物實例扣除建物成本：營造施工費標準表、耐用年數、殘價率、費率 | 離線、推定 | `rules/building_cost.json`，新北市附表一-2 原為圖片逐格抄，標「需估價師確認」 |
| 黑客松命題文件、競賽環境規範 | 題目範圍；Bedrock 請求每秒一次以下 | 離線 | `docs/reference/` |

## 二、地政局提供的範本與基準表

授權：地政局提供，僅供本專案使用。基準明細表轉成 `rules/*.json`，引擎只讀 JSON；新基準表等於新檔案，不改程式。

| 名稱 | 系統用途 | 狀態 | 位置 |
|---|---|---|---|
| 查估書表範本（六頁） | 版面與格線；驗收基準：表 5-2 每個等級、表 4 每個差異率、13.00%、212,958（`tests/test_acceptance.py`） | 離線 | `docs/reference/查估書表範本.pdf`、`fixtures/sample_P002-00_表1表5表4.xlsx` |
| 地政局正式範本 xlsx 三份（表 3、表 4、表 5） | `app/output/official_xlsx.py` 直接寫值輸出 | 離線 | `backend/app/templates/official/`；格位對照 `docs/12_official_templates.md` |
| 評價基準明細表範例（金山區商業用地） | 規則引擎級距與修正率矩陣 | 離線 | `rules/jinshan_commercial_regional.json`、`…_individual.json` |
| 決賽題目評價基準明細表（樹林區普通住宅用地，PDF p.4-26～4-34） | 決賽案件基準表，每條記 PDF 頁碼 | 離線 | `rules/shulin_residential_regional.json`、`…_individual.json` |
| 示範用住宅基準表 | demo 住宅變體；項目依內政部附件、級距沿用金山假設 | 離線、非官方 | `rules/demo_residential_*.json` |
| 設施與量測方式對照 | 每類設施用直線或步行、起點約定、來源機關字串 | 離線 | `rules/facility_measurement.json` |
| 鄉鎮市區鄰接關係 | 比較標的擴大搜尋（辦法 §19 第 2 項） | 離線 | `rules/ntpc_district_adjacency.json`，人工整理 |
| 驗收案例 fixtures | 金山 P002-00、樹林 1110901 案件與幾何估計 | 離線 | `fixtures/` |

## 三、政府開放資料集

授權：政府資料開放授權條款第 1 版，需標示來源機關與資料集名稱。

| 資料集 | 機關 | 系統用途 | 狀態 | 取得方式與落地位置 |
|---|---|---|---|---|
| 不動產實價登錄批次下載（土地買賣） | 內政部地政司 | 自動選比較標的、正常單價、審查重點 v | 離線 | `plvr.land.moi.gov.tw/DownloadSeason?season={季}&type=zip&fileName=lvr_landcsv.zip`（`scripts/fetch_lvr.py`，新北代碼 f）→ `data/lvr/f_land.json`；`app/market/lvr.py` |
| 都市地價指數半年報（附錄三／四／五） | 內政部地政司 | 期日調整（辦法 §17），至第 65 期 114H2，基期 112.3.31＝100 | 離線 | `pip.moi.gov.tw/Upload/sys/cityprice/{period}_market.pdf`（`scripts/fetch_land_index.py`）→ `rules/land_price_index.json`；`app/market/index.py` |
| 新北市都市計畫使用分區 shapefile（34,190 面，TWD97，欄位 ZONE） | 城鄉發展局 | 使用分區、使用分區圖、道路闢建程度、計畫道路寬度 | 離線 | `urban.planning.ntpc.gov.tw/opendataDownload/新北市使用分區.zip`（zip 內檔名 cp950）→ `scripts/build_zoning_db.py` → `data/zoning/ntpc_zoning.sqlite`；`app/maps/zoning.py`、`app/spatial/planned_road.py`。ZONE 只到「商業區」沒有第 X 種 → 細分區仍靠計畫書或人工 |
| 第三代淹水潛勢圖（新北市 6／12／24 小時 10 情境） | 水利署（data.gov.tw 25766） | 勘查表排水之良否 | 離線、推定 | `data/flood/ntpc_24h350r.geojson`（24 小時 350 mm，`FLOOD_SCENARIO` 可切）；`app/spatial/survey_draft.py` |
| 環境保護許可管理系統對象基本資料 ems_s_01（全國 452,346 筆） | 環境部 | 列管污染源，只取空污加水污或毒化物列管者 | 離線 | `data.moenv.gov.tw/api/v2/ems_s_01`（平台公開金鑰分頁抓）→ `data/sources/ems_s_01_pollution_sources.geojson` → `data/poi_ntpc.sqlite`（pollution_source） |
| 全國商圈盤點清冊（新北 32 個商圈） | 商業發展署（data.gov.tw 103804） | 接近商圈；只有文字範圍，用路網圍面 | 離線 | `data/sources/全國商圈盤點清冊.csv` → poi 庫（commercial_district）；對不到路名者人工標定 |
| 路邊停車空位查詢 | 新北市交通局（data.gov.tw 122901） | 停車方便性 | 離線、推定 | `scripts/fetch_ntpc_parking.py` → `data/sources/ntpc_roadside_parking.csv` → poi 庫（roadside_parking） |
| 高速公路交流道座標（11 條國道 181 筆） | 高速公路局（data.gov.tw 166496） | 交流道距離 | 離線 | `data/sources/freeway_interchanges.csv` → poi 庫（highway_interchange） |
| 台灣中油加油站服務資訊（1,972 站） | 台灣中油（data.gov.tw 6065） | 嫌惡設施 | 離線 | `data/sources/cpc_gas_stations.csv` → poi 庫（gas_station） |
| 新北市公告土地現值逐地號 110–113 年 | 新北市資料開放平臺（8d6485f1、21466356、aaa79697、a8f022db） | 同值相鄰宗地推定地價區段、登記面積佐證 | 離線、推定 | JSON API 可帶 segment、lid（CSV 整檔被截在 1,048,575 列，樹林 111 年要走 API）→ `data/sources/ntpc_land_value_jinshan_113.csv`；`bootstrap.sections_from_land_values`、`POST /api/bootstrap/sections_by_land_value`。尚未接進 market/index |
| 營造工程物價指數（月，至 115 年 7 月） | 新北市主計處（data.gov.tw 125690） | 建物成本物價指數調整 | 離線 | `rules/cci_ntpc.json`，每月補一列 |
| 新北市都市計畫公告與計畫書 PDF（49 計畫區） | 城鄉發展局 | 建蔽率、容積率（見第一類） | 線上抓取後離線 | `data/zoning_rules/{pdf,announcements.json,cityplans.json,extracted.json,merged.json}` |
| 台電變電所電磁場資訊 | 台灣電力 | 變電所點位 | 未採用 | `data/sources/taipower_substation_emf.zip`，地址只到路名，改人工標定 |
| 人工標定設施 | 現勘、估價師 | OSM 與政府資料都沒有的設施（金山變電所、福緣納骨堂、老街商圈） | 離線 | `POST /api/spatial/poi` → `data/sources/manual_poi.geojson`，啟動自動併入 |
| 資料集清單 manifest | — | `build_poi.py` 統一轉檔 | 離線 | `data/sources/manifest.json` |

尚未落地，目前以 OSM 代用或留人工填：

- 教育部各級學校（school，I15）、經濟部公有零售市場（R4-1／I16）、新北市公園（R4-2／I17）、內政部殯葬設施、經濟部能源署加油站、環境部焚化爐與掩埋場、金管會金融機構與中華郵政據點（R7-2）、觀光署景點與旅宿（R4-3／R7-4）、國土署路網數值圖道路等級（I13）、新北市停車場。
- 交通部 TDX 運輸資料（公車站牌、客運站、台鐵／高鐵／捷運站、停車場、景點）：**需申請** `https://tdx.transportdata.tw`（`TDX_CLIENT_ID`／`TDX_CLIENT_SECRET`），端點清單 `docs/08` C-9；未申請，現以 OSM 站牌代用。
- 公告現值地價區段圖 shapefile：非開放資料，**需地政局提供**；備援為公告現值同值相鄰宗地推定。

## 四、OpenStreetMap 衍生資料

授權 ODbL。`data/poi_ntpc.sqlite`、`data/osm/*.sqlite` 為 OSM 衍生資料庫，散布時須保留「© OpenStreetMap contributors」並同授權。

| 來源 | 系統用途 | 狀態 | 落地位置 |
|---|---|---|---|
| Geofabrik `taiwan-latest.osm.pbf`（約 165 MB） | 下列各項母檔 | 離線 | `https://download.geofabrik.de/asia/taiwan-latest.osm.pbf` → `scripts/build_osm_ntpc.py` |
| 有名道路 74,472 條 | 街廓圍面、四至草稿、道路寬度、路名投票 | 離線 | `data/osm/roads.sqlite`（`ROADS_DB`） |
| 全部 highway 191,251 段 | 內建步行圖（Dijkstra），OSRM 備援 | 離線、備援 | `data/osm/walk.sqlite`（`WALK_DB`）、`data/osm/walk_cache/`（`scripts/prebuild_walk.py`） |
| 設施點位 57,343（含 shop 20,501） | 設施距離；店舖毗連狀態、顧客通行量推定；超市／量販 `shop=supermarket|mall`、變電所 `power=substation`、高壓鐵塔 `power=tower`、百貨／電影院以 OSM 標籤代用 | 離線、推定 | `data/osm/poi_osm.sqlite` → `data/poi_ntpc.sqlite`（`POI_DB`） |
| 鄉鎮市區界（admin_level 7、8） | 依行政區取範圍 | 離線 | `data/osm/districts.geojson`（`scripts/build_districts.py`） |
| 門牌 3,673,486 筆 | 無地籍界線之比較標的位置推定（`address_estimate`） | 離線、推定 | `data/osm/addresses.sqlite`（`scripts/build_addresses.py`）；`app/spatial/locate.py` |
| Overpass API | 單一鄉鎮重抓設施 | 線上、備援 | `scripts/build_poi.py --overpass bbox`；主站 `overpass-api.de`，備援 `overpass.kumi.systems`、`overpass.private.coffee` |

OSM Nominatim 地理編碼評估後放棄，台灣中文地址查不到。金山單區舊檔（`data/poi_osm_jinshan.sqlite`、`data/roads_osm_jinshan.geojson`、`data/walk_graph_jinshan.geojson`、`data/zoning/jinshan_zoning.geojson`）已被全區庫取代，僅備援。

## 五、地圖與圖磚服務

唯一在會場需要外網的一類。底圖走後端代理並快取，賽前用 `scripts/prefetch_tiles.py` 預抓指定鄉鎮。

| 名稱 | 提供者 | 系統用途 | 狀態 | 位置 |
|---|---|---|---|---|
| WMTS 電子地圖 EMAP | 內政部國土測繪中心（免申請，標「© 國土測繪中心」） | 三張圖說 PNG 與互動地圖底圖 | 線上、可預抓 | `https://wmts.nlsc.gov.tw/wmts/{layer}/default/GoogleMapsCompatible/{z}/{y}/{x}`；`GET /api/tiles/{z}/{x}/{y}`；快取 `data/tiles/`（`TILE_CACHE`）；`app/maps/render.py` |
| WMTS／WMS 段籍圖 LANDSECT | 同上 | 區段略圖與區段圖疊段界、段名 | 線上、可預抓 | 同上 `layer=LANDSECT`；WMS `https://wms.nlsc.gov.tw/wms`（4326／3826／3857） |
| 圖層清單 API、對外 IP 查詢 | 國土測繪中心（data.gov.tw 139248） | 查圖層代碼；申請 API 綁 IP | 線上 | `https://api.nlsc.gov.tw/other/MapLayerInfo/<代碼>`、`https://api.nlsc.gov.tw/IP` |
| AWS Terrain Tiles（Mapzen terrarium，SRTM 約 30 m） | AWS Open Data，免金鑰 | 宗地與區段地勢高亢或低窪（手冊 p.23） | 線上、可快取、推定 | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`（z=14）；`app/spatial/terrain.py`；快取 `data/terrain/14/`；`TERRAIN_OFFLINE=1` 關閉；可換內政部 20 m DEM（data.gov.tw 35430／176927） |
| Google Maps | Google | 只供人眼讀座標 | 不採用 | 條款不允許離線儲存，底圖一律 NLSC |

## 六、地籍幾何

`app/spatial/cadastre.py` 依序嘗試，每筆寫 `geometry_source`／`geometry_note`，介面必須顯示。

| 順位 | 來源 | 狀態 | 位置與設定 |
|---|---|---|---|
| 1 | 需用土地人函送地籍圖（GeoJSON、KML／GML、Shapefile zip，TWD97）；查估辦法 §5、§20 本來就要送 | 離線 | `FileCadastreProvider`；`CADASTRE_GEOJSON`，預設 `data/cadastre/default.geojson`；案件匯入 `POST /api/cases/{id}/cadastre` → `data/cadastre/cases/<id>.geojson`；示範檔 `data/示範_地籍圖_金山P002-00.geojson` 為合成非真地籍 |
| 2 | g0v 地號查詢開放 API（資料來自內政部地籍圖資網路便民服務系統；縣市,段名,地號 → 宗地多邊形） | 線上、推定 | `TwlandCadastreProvider`，`https://twland.ronny.tw/index/search`；快取 `data/cadastre/twland_cache.json`；`TWLAND_OFFLINE=1` 關閉。免申請、非即時，界線標「推定／外部開放資料」，正式以地政局地籍圖為準。決賽題目樹林 5 筆全部查到 |
| 3 | 國土測繪中心地籍查詢 API：CAD_004（地段號→坐標）、MAP_001／MAP_002（向量）、CAD_010、TILE_001 地籍圖磚 | 需申請 | `NLSCCadastreProvider` 介面留空；`NLSC_API_KEY`、`NLSC_CAD_ENDPOINT`；申請 (04)2252-2966#256，綁 URL／IP、主機須在境內非陸資雲、民營付費；文件 `docs/reference/{申請服務介接說明表,免申請服務介接說明表,網路服務介接申請書}.pdf` |
| 4 | 質心加清冊面積寬深合成矩形 | 備援 | `synthesize_parcel_geometry`，`geometry_source=synthetic`，示意非地籍 |
| 附 | 國土測繪中心段代碼 API（ListCounty／ListTown／ListLandSection，免申請） | 線上、已快取 | `https://api.nlsc.gov.tw/other/…`；`data/cadastre/nlsc_codes.json`（金山區 F25、金美段 1027、溫泉段 1026） |
| 附 | 地價區段圖匯入（GeoJSON、KML、GML、SHP zip） | 離線 | `POST /api/cases/{id}/sections_map` → `data/cadastre/cases/<id>_sections.geojson`，來源 `section_map`；示範 `data/示範_地價區段圖_金山.geojson` |

## 七、路徑與距離量測

順序 OSRM → 內建步行圖 → 直線乘 1.3；`provenance.router` 記來源。

| 來源 | 說明 | 狀態 | 位置 |
|---|---|---|---|
| OSRM foot profile | 自架容器，資料仍是 Geofabrik 台灣檔；本機無 docker，改在 EC2 跑 | 自架服務 | `OSRM_URL`；`app/spatial/osrm.py`、`deploy/osrm.md`、`docker-compose.yml` |
| 內建 OSM 步行圖 | Dijkstra，排除 motorway／trunk、foot=no、access=private | 離線、備援 | `app/spatial/walking.py` |
| 直線乘 1.3 | 最後備援，量測方式 `straight_estimated` | 備援、推定 | `app/spatial/distance.py` |
| AWS Location Service | 文件列為備選 | 未使用 | — |

## 八、語言模型

只用於掃描件辨識（`app/adapters/pdf_forms_vision.py`）與意見書潤飾（`app/report/opinion.py`）。等級、修正率、價格全由規則引擎確定性計算。

| 供應商 | 設定 | 狀態 | 位置 |
|---|---|---|---|
| Anthropic 官方 API | `LLM_PROVIDER=anthropic`、`ANTHROPIC_API_KEY`、`ANTHROPIC_MODEL_ID`（預設 `claude-opus-5`） | 線上、需金鑰 | `app/llm/anthropic_provider.py` |
| Amazon Bedrock（boto3 Converse） | `LLM_PROVIDER=bedrock`、`AWS_REGION`、`BEDROCK_MODEL_ID`（EC2 預設 `us.anthropic.claude-sonnet-4-5-20250929-v1:0`）；競賽規範每秒一次以下，`BEDROCK_MIN_INTERVAL` 預設 1.1 秒 | 線上、需開通 | `app/llm/bedrock_provider.py`、`deploy/provision.sh`、`deploy/runbook_ec2.md` |
| mock provider | 測試用；未設任何金鑰時掃描件流程停用，首頁狀態列會顯示 | 離線 | `app/llm/mock_provider.py` |

## 九、字型與第三方資產

| 名稱 | 用途 | 授權 | 位置 |
|---|---|---|---|
| 文泉驛微米黑 `wqy-microhei.ttc` | PDF 書表與意見書中文字型（reportlab，subfontIndex） | Apache 2.0 | `backend/app/fonts/`（含 `LICENSE.txt`） |
| 系統字型候選（PingFang、STHeiti、Hiragino、Noto CJK、文泉驛） | 圖說 PNG 中文標籤；`MAP_FONT` 可覆寫；都沒有就不畫中文並在圖上註明 | 依系統 | `app/maps/render.py`（`FONT_CANDIDATES`） |
| certifi、Leaflet、Next.js、FastAPI、shapely、pyproj、osmium、openpyxl、reportlab、python-docx、PIL | 抓 NLSC 圖磚的 TLS 憑證；程式庫 | 各開源授權 | `frontend/package.json`、`backend/pyproject.toml`、`requirements.lock` |

## 十、部署依賴

非估價資料，列出以便當天知道要開哪些外網：AWS EC2（us-west-2）、EC2 metadata、`checkip.amazonaws.com`、NodeSource、Caddy（cloudsmith）、Docker apt 來源、GitHub 私有 repo 自動部署。見 `deploy/provision.sh`、`deploy/runbook_ec2.md`。

## 資料進庫規範

`backend/scripts/build_poi.py` 把每個來源轉成統一列（manifest 格式見檔頭 docstring；`--overpass bbox` 補 OSM 類別，可重複執行合併）：`type, name, lon, lat, geom(WKT), source, source_id, attrs(json)`。
座標統一 WGS84 存，計算時投影 EPSG:3826。每筆保留 `source` 字串，直接出現在表格的「來源」欄。

## 歷程備註（金山範本驗證）

- `scripts/check_jinshan_realdata.py`：用範本比準地四個距離（學校 150、市場 30、公園 190、站牌 80 m）反推位置，RMS 殘差 52 m；OSM 直線距離 212／59／264／104 m，市場、公園、站牌與範本同級距，學校差一級（OSM 學校點是校區質心，校門口會更近；面狀設施應取邊界最近點）。
- 區段 bootstrap：以範本提示點用 `block_from_roads` 圍出 20,092 m² 街廓，四至草稿三邊與範本一致（西、東要人工改）。
- 範本點名設施在庫裡的有金山國小、金美國小、金山第一市場、中山溫泉公園、金包里老街停車場、中油金山站等；金山變電所、福緣納骨堂、老街商圈以人工標定補。

## 版權／授權彙整

命題文件、作業手冊、書表範本、基準明細表由地政局提供，僅供本專案；國土測繪中心 WMTS 與段籍圖免申請，標「© 國土測繪中心」；OSM 衍生資料 ODbL，標「© OpenStreetMap contributors」；政府開放資料集依政府資料開放授權條款第 1 版標示機關與資料集；高程 AWS Terrain Tiles（Mapzen terrarium）；人工標定標「人工標定（來源：現勘／估價師）」。前端頁腳與 `README.md` 「授權與來源」同步。
