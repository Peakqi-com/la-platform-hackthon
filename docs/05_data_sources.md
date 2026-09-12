# 05 資料來源（政府開放資料優先）

原則：全部賽前下載進 `data/`，當天不打外部 API；只有底圖 tile 線上拉。
「確認」欄：✅ 已查證頁面存在；🔍 憑印象，抓之前要到 data.gov.tw / data.ntpc.gov.tw 對一下資料集名稱與欄位。

| 需求 | 來源 | 用途 | 確認 |
|---|---|---|---|
| 底圖、段籍圖層 | 國土測繪中心 WMTS `https://wmts.nlsc.gov.tw/wmts`（EPSG:3857）、WMS `https://wms.nlsc.gov.tw/wms`；電子地圖 `EMAP`，段籍圖 `LANDSECT`（WMS 支援 4326/3826/3857） | 三張圖底圖 | ✅ data.gov.tw/dataset/17220 |
| 圖層清單 | `https://api.nlsc.gov.tw/other/MapLayerInfo/<代碼>` | 查可用圖層 | ✅ data.gov.tw/dataset/139248 |
| 宗地幾何（段/地號→座標、面積） | 國土測繪中心地籍圖資便民服務 API；新北市地政局「土地段代碼對照表」 | 宗地質心、多邊形 | 🔍 多邊形能否用 API 取得要實測；拿不到就從清冊手填面積寬深 |
| 都市計畫使用分區、計畫道路寬度 | 新北市城鄉發展局，`data.ntpc.gov.tw` 開放「都市計畫土地使用分區」及「都市計畫範圍」圖資下載 | 分區圖、行政條件、道路寬度 | ✅（2024-01 開放） |
| 地價區段（劃分起點） | 公告土地現值地價區段圖資（各縣市 shapefile，data.gov.tw） | 深模式 bootstrap | 🔍 |
| 買賣實例 | 內政部實價登錄批次下載 `plvr.land.moi.gov.tw/DownloadSeason?season=114S2&type=zip&fileName=lvr_landcsv.zip`（`scripts/fetch_lvr.py` → `data/lvr/f_land.json`；純土地＋房地，含每筆地號與細分區） | 自動選比較標的（`app/market/lvr.py`）；審查重點 v | ✅ 2026-09-09 抓 113S3～114S3 新北 65,362 筆 |
| 都市地價指數 | 內政部地政司半年報 PDF `pip.moi.gov.tw/Upload/sys/cityprice/114H2_market.pdf` 附錄三／四／五（各鄉鎮市區 住／商／工 各期指數，基期 112.3.31＝100；`scripts/fetch_land_index.py` → `rules/land_price_index.json`） | 期日調整（`app/market/index.py`） | ✅ 第 65 期，109.9.30～114.9.30 共 11 期 |
| 學校 | 教育部全國各級學校基本資料 | I15 / 住宅用地區域因素 | 🔍 |
| 傳統市場 | 經濟部公有零售市場資料 | R4-1 / I16 | 🔍 |
| 超市、量販 | OSM `shop=supermarket`, `shop=mall` | R4-1 / I16 | 例外（政府無完整） |
| 公園 | 新北市公園資料（`data.ntpc.gov.tw`） | R4-2 / I17 | 🔍 |
| 公車站牌、客運站、台鐵/高鐵/捷運站 | 交通部 TDX（需申請 key，賽前抓好落地） | R2-3 / R2-4 / I18 | 🔍 |
| 交流道 | 高公局「高速公路交流道座標」11 條國道 CSV（data.gov.tw 166496，WGS84）→ `data/sources/freeway_interchanges.csv` → 設施庫 highway_interchange 181 筆 | R2-5 | ✅ 2026-09-09 |
| 停車場 | 新北市停車場資料 / TDX 停車場 | R4-4 | 🔍 |
| 公墓、納骨塔、殯儀館、火葬場 | 內政部殯葬設施資料 | R5-2 / I20 | 🔍 |
| 加油站 | 經濟部能源署加油站資料 | R5-1 / I20 | 🔍 |
| 變電所、高壓鐵塔、瓦斯槽 | OSM `power=substation`, `power=tower`（台電開放資料有限） | R5-1 / I20 | 例外 |
| 焚化爐、掩埋場、污水處理廠 | 環境部設施資料 | R5-3 / I20 | 🔍 |
| 污染源 | 環境部列管事業 | R6-1 | 🔍 |
| 金融機構 | 金管會/中央銀行金融機構分支據點；中華郵政據點 | R7-2 | 🔍 |
| 觀光景點、旅宿 | 交通部觀光署景點/旅宿開放資料（TDX 觀光） | R4-3 / R7-4 | 🔍 |
| 百貨、電影院 | OSM + 人工標定 | R7-1 / R7-3 | 例外 |
| 店舖點位 | OSM shop=*（全區 20,501 筆）→ 設施庫 shop | 店舖毗連狀態、顧客通行量推定 | 例外（政府無店舖點位） |
| 全區 OSM 圖資 | Geofabrik taiwan-latest.osm.pbf → `scripts/build_osm_ntpc.py` → `data/osm/roads.sqlite`（有名道路 74,472）、`walk.sqlite`（highway 191,251）、`poi_osm.sqlite`（設施 57,343）、`districts.geojson`（鄉鎮市區界，admin_level=7）；依案件 bbox 局部載入（`app/spatial/geodb.py`） | 路網、步行圖、設施距離、行政區範圍 | ✅ 2026-09-10 |
| 地籍界線（免申請） | g0v「地號查詢」開放 API（https://twland.ronny.tw，資料來自內政部地籍圖資網路便民服務系統；縣市,段名,地號 → 宗地多邊形，同段名跨區以鄉鎮篩）→ `spatial/cadastre.TwlandCadastreProvider`，快取 `data/cadastre/twland_cache.json`；順序在地籍圖檔之後、NLSC API 之前，界線標「推定／外部開放資料」 | 比準地與比較標的界線、面積、寬深、形狀 | ✅ 2026-09-12（決賽題目樹林 5 筆全部查到；非即時，正式以地政局地籍圖為準；`TWLAND_OFFLINE=1` 關閉） |
| 公告土地現值（逐地號） | 新北市資料開放平臺 110（8d6485f1）、111（21466356）、112（aaa79697）、113（a8f022db）年公告土地現值；JSON API 可帶 segment、lid 篩選（CSV 整檔匯出被截在 1,048,575 列，樹林區 111 年在檔外，要走 API） | 期日調整（平均區段地價表替代）、比準地登記面積佐證 | 🔍 2026-09-12 抓法確認，尚未接進 market/index |
| 門牌定位 | OSM addr:street＋addr:housenumber（新北一帶 3,673,486 筆）→ `scripts/build_addresses.py` → `data/osm/addresses.sqlite`（name 索引） | 無地籍界線之比較標的位置推定 | ✅ 2026-09-11 |
| 全區使用分區 | 城鄉局使用分區 shapefile 34,190 面 → `scripts/build_zoning_db.py` → `data/zoning/ntpc_zoning.sqlite`（R-tree） | 使用分區、道路闢建程度、分區圖 | ✅ 2026-09-10 |
| 淹水潛勢圖 | 經濟部水利署第三代淹水潛勢圖（data.gov.tw 25766，新北市 7z：6／12／24 小時 10 情境 shp）→ `data/flood/ntpc_24h350r.geojson`（24 小時 350 mm，屬性 class／depth_m） | 排水之良否推定 | ✅ 2026-09-10 |
| 污染源 | 環境部環境保護許可管理系統對象基本資料 ems_s_01（全國 452,346 筆，WGS84）→ 篩「空污＋水污」或「毒化物」列管者 → 設施庫 pollution_source | R6-1 污染源 | ✅ 2026-09-10 |
| 建物成本價格 | 估價師公會全聯會第四號公報 113.12.11 版（營造施工費標準表新北市附表一-2 為圖片，逐格抄成 `rules/building_cost.json`；耐用年數、殘價率、費率為文字層） | 含建物實例之土地正常單價（§13 第3、4款） | ✅ 2026-09-10（推定，需估價師確認） |
| 路邊停車格 | 新北市交通局「路邊停車空位查詢」CSV（data.gov.tw 122901，每格經緯度／類型／收費；`scripts/fetch_ntpc_parking.py`）→ 設施庫 roadside_parking | I21 停車方便性推定 | ✅ 2026-09-10 |
| 商圈 | 經濟部商業發展署全國商圈盤點清冊（data.gov.tw 103804，文字範圍）→ 路網圍面 → 設施庫 commercial_district | I19 接近商圈 | ✅ 2026-09-10（對不到路名者需人工標定） |
| 高程 | 衛星測高高程資料 AWS Terrain Tiles（Mapzen terrarium，SRTM 等，約 30 m；`data/terrain` 快取，`terrain.prefetch(bbox)` 預抓） | 宗地與區段地勢推定 | 例外；內政部 20 m DEM（data.gov.tw 35430／176927）可替換 |
| 道路等級 | 國土署路網數值圖（道路等級屬性） | I13 | 🔍 都計外只能手填 |
| 步行路徑 | **無政府路徑引擎** → OSRM + Geofabrik 台灣 OSM，foot profile（`deploy/osrm.md`） | walking 距離 | 例外；備選 AWS Location Service |

## 目前已落地的資料（2026-09-06）

- `data/poi_osm_jinshan.sqlite`：OSM Overpass 抓金山區 bbox `25.20,121.60,25.26,121.68`，2,662 筆（含加油站 1,976、交流道 181；現由 `data/poi_ntpc.sqlite` 全區庫取代，僅備援）：bus_stop 101、hv_tower 97、parking_lot 70、cemetery 15、park 15、plaza 10、tourist_hotel 8、school 6、tourist_attraction 5、gas_station 4、bank 4、supermarket 3、pedestrian_zone 3、traditional_market 2、intercity_bus_station 2、columbarium 2、substation 1、post_office_bank 1。
  範本點名的設施在庫裡：金山國小、金美國小、金山第一市場、中山溫泉公園、金山區公所（站牌）、金包里老街停車場、中油金山站、金山地區農會、新北北海溫泉洲際酒店、國光客運金山站、金山區第一公墓。
  **缺**：金山變電所（OSM 只有「開關場」）、福緣納骨堂、老街商圈（無 tag）、金山區第一公墓（改抓多邊形後名稱遺失，待查 tag）→ 需人工標定或政府資料。
- 真實資料自洽檢查 `scripts/check_jinshan_realdata.py`：用範本比準地四個距離（學校 150、市場 30、公園 190、站牌 80）反推位置，RMS 殘差 52 m；
  直線距離 212 / 59 / 264 / 104 m → 市場、公園、站牌與範本同級距，**學校差一級**（範本 150 m 優、OSM 直線 212 m 稍優）。
  可能原因：範本量的是宗地邊界或步行路徑起點不同、OSM 學校點是校區質心（校門口會更近）。→ 決賽拿到地籍座標後再對；面狀設施應取邊界最近點（`geo.straight_distance_m` 對多邊形已是如此，但 OSM 學校抓到的是 center 點）。
- `data/roads_osm_jinshan.geojson`：OSM 有名道路 294 段（highway 等級保留，`bootstrap` 只用 primary/secondary/tertiary/residential/unclassified/pedestrian 切街廓）。
- `data/zoning/jinshan_zoning.geojson`：新北市城鄉局「新北市使用分區」shapefile（TWD97，78 MB，`https://urban.planning.ntpc.gov.tw/opendataDownload/新北市使用分區.zip`，zip 內檔名 cp950）裁金山 bbox 399 筆；欄位只有 `ZONE`（商業區／住宅區…），**沒有「第二種」細分** → 只能當建議，R1-2／I22 的細分區仍要人工填。
- 地籍多邊形：NLSC 開放 API 只有段代碼；「地籍查詢API」CAD_004（地號→座標）與 MAP_001 須向國土測繪中心申請（(04)2252-2966#256）。決賽合理路徑是需用土地人依查估辦法 §5、§20 提供地籍圖（shp/DXF）→ `CADASTRE_GEOJSON`。
- 區段 bootstrap 真實資料檢查：以範本提示點（比準地反推點、金山第一市場、金山區公所站）用 `block_from_roads(exclude 中山路新市場)` 圍出 20,092 m² 街廓，邊界道路 中山路/中正路/仁愛路/信義路/和平街/慈護街/福德街/金包里街；四至草稿「北側至金包里街，南側至中山路，西側至中山路，東側至慈護街」（範本：北 金包里街、南 中山路、西 中正路、東 福德街 → 西/東要人工改）。
- `data/walk_graph_jinshan.geojson`：OSM 全部 highway 1,729 條 way（含 footway/steps/service），內建步行圖用；`walking.py` 排除 motorway/trunk、foot=no、access=private。
- `data/sources/cpc_gas_stations.csv` + `manifest.json`：中油加油站 1,972 站（經緯度），已進 POI 庫（金山站 121.6336, 25.2247）。
- `data/sources/ntpc_land_value_jinshan_113.csv`：新北市 113 年公告土地現值金山區 25,244 筆（欄位 segment/lid/official_value_busiprval；lid 為 8 碼地號，489 → 4890000）。
- `data/sources/manual_poi.geojson`：人工標定設施（`POST /api/spatial/poi`）。
- 未做：OSRM（本機無 docker，改 EC2）、TDX（要 key）、其他政府資料集；步驟見 docs/08 C 節。

## 資料進庫規範

`backend/scripts/build_poi.py` 把每個來源轉成統一列（manifest 格式見檔頭 docstring；`--overpass bbox` 補 OSM 類別，可重複執行合併）：`type, name, lon, lat, geom(WKT), source, source_id, attrs(json)`。
座標統一 WGS84 存，計算時投影 EPSG:3826。每筆保留 `source` 字串，這會直接出現在表格的「來源」欄。

## 版權/授權

政府資料開放授權條款第 1 版可商用、需標示來源；OSM 為 ODbL，需標示 © OpenStreetMap contributors；國土測繪 WMTS 免申請。
