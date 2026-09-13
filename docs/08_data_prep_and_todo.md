# 08 資料準備操作指南與待辦（2026-09-06 整理）

## A. 待辦（需要人處理的，依「能先做」排序）

### 決賽題目（樹林區普通住宅用地，2026-09-12）全自動化還缺的資料
- [~] **收益法（2026-09-13 上線，選用）**：租賃實價登錄 → `scripts/fetch_lvr_rent.py` 產生 `data/lvr/f_rent.json`（本機 52,740 筆，110S3～111S3、113S3～114S3）；**正式站要上傳此檔**（`rsync -e 'ssh -i ~/.ssh/ntpc-key.pem' data/lvr/f_rent.json ubuntu@54.188.82.141:/opt/app/data/lvr/`），否則搜尋收益實例回「尚無租賃資料」。土地（素地）租賃實例很少：樹林區 111.03.02～111.09.01 住宅區只有 1 筆（東昇段 22 m²，月租 851 元/m²），多數備註有地上建物需情況調整；比準地公告地價（地價稅）與閒置月數、資本化率溢酬需估價師填或確認。
- [ ] **房租指數只到 112 年 8 月**：`rules/cpi_rent.json` 取自主計總處銜接表舊檔（ws.dgbas.gov.tw），新網址 stat.gov.tw 擋程式下載（403）、開放資料平臺無全國房租指數 CSV；估價基準日在 112.08 之後的案件，收益實例價格日期調整會取 112.08 指數（note 已註明），需手動下載新版銜接表後重跑 `scripts/fetch_income_rates.py`，或人工填調整率。
- [x] **正式環境**：https://54.188.82.141.sslip.io/（AWS us-west-2，2026-09-12 部署，push 到 main 自動更新；部署細節見 `deploy/runbook_ec2.md`）。2026-09-13 發現主機 `/api/health` 回 500 且「依地號產生」回 500（主機 `data/lvr/f_land.json` 缺檔，其餘原因要看 `journalctl -u ntpc-backend`）；健康檢查已改成單項壞掉不影響整體、依地號產生失敗會把原因回給畫面，待自動部署套用後再看 `/api/health` 的 errors 欄。
- [x] **樹林區地籍界線**：改用 g0v 地號查詢開放 API（免申請）自動抓比準地與比較標的界線（2026-09-12）；正式版仍建議向主辦要地籍圖或申請 NLSC，開放資料非即時。區段內其他宗地仍無界線（只影響區段圖美觀，不影響計算）。
- [~] **比準地樹德段1415 面積**：開放地籍界線算出 25.44 m²（登記面積待地籍謄本核對）。
- [ ] **新北市樹林區土地平均區段地價表（住宅區）110、111 年**：表4 期日調整 5.96%／4.09%／5.49% 的依據（不是都市地價指數）；拿到後在 `rules/` 加一份指數表並讓 `market/index.py` 可切換來源。
- [x] 地價區段圖 P001～P004：四至文字自動圍面四個都成功（2026-09-12；P001 缺 啟智街187巷24弄 與未開闢計畫道路，面積 2,695 m² 偏小，需確認）。
- [x] 樹林住宅基準表 → `rules/shulin_residential_*.json`（2026-09-12）。
- [x] 實價登錄 110S3～111S3 已下載；比較標的1 實價登錄單價 131,667 ≠ 表4 填載 130,167（待向地政局確認是情況調整還是填載錯誤）。
- [x] 地政局正式範本 xlsx 寫入器（表3／表5-1／表4）：`app/output/official_xlsx.py`，格位對照 docs/12。
- [x] 題目 PDF 直接上傳即可跑完全程（解析四張勘查表、自動依地號產生、表5 免修正）：docs/12 末節。

| # | 事項 | 誰 | 怎麼做 | 沒做的影響 |
|---|---|---|---|---|
| 1 | 開 Excel 目視 `fixtures/sample_P002-00_表1表5表4.xlsx` 三張表版面 | 你 | 對照 `docs/reference/查估書表範本.pdf` p.1–3 | 版面細節走樣 |
| 2 | 向地政局確認疑點 B（二級細項等級數字欄：手冊 p.49／p.52「1 優 2 劣」vs 範本「1 無」「1｜2」；系統已改依手冊） | 你 | 一句話問承辦 | 表1/表5 數字欄可能與現行慣例不符 |
| 3 | 人工標定 OSM 沒有的設施：金山變電所（台電資料只到「中正路」）、福緣納骨堂（金山區第一公墓內，磺港路 16-1 號）、老街商圈範圍 | 你或當天操作 | `POST /api/spatial/poi`（type、name、lon、lat），或編輯 `data/sources/manual_poi.geojson`；座標可用 Google Maps 右鍵「這是哪裡」讀出來後手動輸入（只抄座標，不存 Google 資料） | 表5 特殊設施、表4 商圈無法自動算 |
| 4 | 問主辦：當天會不會給預定徵收範圍地籍圖（shp/DXF）？AWS 給的是帳號還是機器？Bedrock 有沒有預開？ | 你 | 一封信 | 地籍圖是最省事的幾何來源（查估辦法 §5、§20 本來就要送） |
| 5 | 申請國土測繪中心地籍查詢 API（CAD_004 地號→座標、MAP_001）作備援 | 你 | 電話 (04)2252-2966 轉 256；拿到規格後填 `NLSC_API_KEY`、`NLSC_CAD_ENDPOINT`，並補 `cadastre.NLSCCadastreProvider.lookup` | 沒地籍圖又沒 API 時只能用質心合成矩形 |
| 6 | TDX 會員申請（公車站牌／客運站／停車場／景點） | 你 | https://tdx.transportdata.tw 註冊 → 取得 client id/secret → 存 `.env` `TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`（賽前抓一次落地即可） | OSM 站牌已有 101 筆，TDX 是補強，不是必要 |
| 7 | 自己 AWS 帳號：MFA、IAM、預算警示、Bedrock 開通（記錄耗時）、EC2 部署彩排（含 OSRM docker） | 你 | 第 6 步時做 | 當天部署風險 |
| 8 | 公告現值地價區段圖 shapefile | 地政局 | 非開放資料；當天若能給最好 | 已有替代：公告現值同值相鄰宗地推定（B-3） |

### 賽前彩排清單（2026-09-08 補）
- [ ] 把比賽地區的地籍圖（GeoJSON，屬性 段名／地號 8 碼）放到 `data/cadastre/default.geojson`：沒有匯入本案地籍圖時，「依地號產生」與實價登錄比較標的都會用它找界線（目前放的是金美段 32 筆示範檔）
- [ ] `cd backend && python3 scripts/fetch_lvr.py --valuation <估價基準日>` 抓實價登錄（新北全區）；換縣市加 `--county`
- [ ] `python3 scripts/fetch_land_index.py --period <最新期 如 114H2>` 更新都市地價指數表
- [ ] `python3 scripts/fetch_ntpc_zoning_rules.py`（全區 49 計畫，PDF 約 0.5～1 GB 存 data/zoning_rules/）→ `python3 scripts/merge_zoning_rules.py` 併入 `rules/zoning_bcr_far.json`；併入後把 `check=true` 的分區對照計畫書核一次（rules 內 note 有 PDF 頁碼）
- [ ] 高程瓦片：`python3 -c "from app.spatial import terrain; print(terrain.prefetch((minlon,minlat,maxlon,maxlat)))"`（金山已抓 16 塊）
- [x] 全區圖資（2026-09-10 已建，換縣市才要重跑）：下載 Geofabrik `taiwan-latest.osm.pbf`（約 165 MB）→ `python3 scripts/build_osm_ntpc.py <pbf>` 與 `python3 scripts/build_districts.py <pbf>`（各約 5 分鐘）→ `data/osm/`
- [x] 門牌定位：`python3 scripts/build_addresses.py <pbf>`（約 5 分鐘）→ `data/osm/addresses.sqlite`（約 1 GB，部署要帶）
- [ ] 部署後 `python3 scripts/prebuild_walk.py` 預建 29 區步行圖快取（`data/osm/walk_cache/`，約 340 MB，2 分鐘；不帶也行，第一次量測時自動建）
- [x] 全區使用分區：`python3 scripts/build_zoning_db.py`（城鄉局 shp → `data/zoning/ntpc_zoning.sqlite`）
- [x] 路邊停車格：`python3 scripts/fetch_ntpc_parking.py`（再跑 build_poi_ntpc 併入）
- [x] 設施資料庫：`python3 scripts/build_poi_ntpc.py --ems <ems_s_01 全部紀錄 jsonl>` → `data/poi_ntpc.sqlite`（OSM 全區＋加油站／交流道＋污染源＋商圈）；ems 紀錄用 curl 分頁抓 `https://data.moenv.gov.tw/api/v2/ems_s_01?api_key=<平台公開金鑰>&limit=1000&offset=N&format=JSON`
- [x] 淹水潛勢圖：data.gov.tw 25766 新北市 7z → `data/flood/ntpc_24h350r.geojson`（已放；換情境改轉其他 shp）
- [x] 商圈：2026-09-11 起對不到路名者以路網關鍵字或範圍文字的車站定位，新北 32 個商圈全部有面；build_poi_ntpc 仍印「需人工標定」時在三張圖頁點圖標定
- [x] 營造工程物價指數：新北市主計處月資料已抄進 `rules/cci_ntpc.json`（至 115 年 7 月）；之後每月從 data.ntpc.gov.tw 資料集 9d0483b6 下載 CSV 補一列（key 為民國年月 5 碼，如 11408）
- [ ] 淹水潛勢情境：預設 24 小時 350 mm（`data/flood/ntpc_24h350r.geojson`）；要換情境先轉檔放同資料夾，啟動時設 `FLOOD_SCENARIO=<檔名中段>`
- [ ] 前端提交前 `cd frontend && npm run lint`（ESLint 9，0 錯誤；警告可留）與 `npm run build`
- [ ] EC2 部署照 `deploy/runbook_ec2.md`（不用 docker：Node 22、`pip install -r requirements.lock`、先起後端再 build 前端）；資料只帶約 400 MB（清單在手冊第 0 節）
- [ ] 部署到 EC2 後先跑 `cd backend && python3 scripts/prefetch_tiles.py`（會場可能沒外網；若主辦給的地區不是金山，改 `--bbox`）
- [ ] 設定 `ANTHROPIC_API_KEY`（或 `LLM_PROVIDER=bedrock` 與 AWS 憑證），否則掃描件 PDF 無法辨識、意見書不能潤飾；首頁狀態列會顯示
- [ ] 首頁按「用範例看一遍」確認審查頁五項不符與「看基準表格位」都正常

### 國土測繪圖資服務雲：地籍圖 API 申請（2026-09-08 查證）
來源：https://maps.nlsc.gov.tw/S09SOA（「申請服務介接說明表」「免申請服務介接說明表」「網路服務介接申請書」已存到 `docs/reference/`）。

| 編號 | 代碼 | 內容 | 回傳 | 申請 |
|---|---|---|---|---|
| MAP_001 | CadasMapQuery | 指定地號查詢地籍圖（向量） | GML／KML／SHP | 要申請（向量服務） |
| MAP_002 | CadasMapPointQuery | 指定坐標查詢地籍圖（向量） | GML／KML／SHP | 要申請（向量服務） |
| TILE_001 | 地籍圖磚 | 地籍圖 WMTS／WMS（有界線與地號的圖磚，**最接近範本底圖**） | 圖磚 | 要申請；民營需訂閱付費（30 萬次/日 2,500 元/月起） |
| CAD_004 | GetLandPositionLongitudeLatitude | 地段號查坐標 | XML | 要申請 |
| CAD_010 | CadasLandNoQuery | 指定範圍查地號清單 | JSON | 要申請 |
| LANDSECT | 段籍圖 | 段界＋段名 | WMTS／WMS | 免申請（系統已用） |

要點：
- 提供對象分三類：學術單位、中央機關／地方政府／國營事業（免費，備函附申請書）、民營團體／公司（審查通過並繳費）。**以新北市地政局名義申請最順**，比賽團隊以公司名義要付費；廠商「開發測試」可勾選 6 個月試用。
- 綁定 URL 或 IP，且切結主機與 IP 均在中華民國境內、非陸資雲端。**部署在境外 AWS 區域（如東京）會不符**，申請時要確認 AWS 區域或改用境內主機。
- 向量服務（WFS_001-018、MAP_001-002）限單位內部使用；「資料轉成圖片再輸出於網站不受此限」，本系統把地籍畫成三張圖說 PNG 正是這種用法。
- API 參數規格在審查通過後提供，公開文件只有清單。系統這邊已備妥：MAP_001／002 回傳的 KML／GML 可直接用「① 輸入資料 → 匯入地籍圖」匯入（自動轉 TWD97 → 經緯度、自動辨認段名／地號欄）；拿到規格後再把 `NLSCCadastreProvider` 接上即可自動查詢。
- 確認伺服器對外 IP：在伺服器上瀏覽 https://api.nlsc.gov.tw/IP。

## B. 三個問題的替代方案評估

**B-1 缺 POI 能不能用 Google Maps？** 可以當「人眼查座標」的工具，不能當資料源。Google Maps Platform 條款不允許把 Places/Geocoding 結果離線儲存或與非 Google 底圖一起顯示，而我們的底圖是國土測繪中心。作法：在 Google Maps 右鍵讀座標，手動輸入 `POST /api/spatial/poi`，來源標「人工標定」。
已試過的自動化替代：OSM Nominatim 對台灣中文地址幾乎查不到（三筆測試皆空）；台電「變電所電磁場資訊」有金山 S/S 但地址只到「中正路」；內政部殯葬設施沒有全國座標檔，新北市民政局的公墓納骨塔清單只有文字。→ 人工標定是最務實的。

**B-2 地價區段圖有沒有替代？** 國土測繪圖資雲 68 個免費 WMS 圖層裡沒有地價區段；新北地政局的地價區段查詢是網頁不是 API。替代：新北市 113 年公告土地現值 CSV（開放資料，已下載 25,244 筆金山區，`data/sources/ntpc_land_value_jinshan_113.csv`，金美段 489 = 55,396、溫泉段 218 = 29,700）＋ 宗地幾何 → 同值相鄰宗地推定同一區段（`bootstrap.sections_from_land_values`、`POST /api/bootstrap/sections_by_land_value`）。前提仍是宗地幾何，所以 A-4 / A-5 優先。

**B-3 OSRM 沒 docker？** 這台機器沒有 docker，OSRM 改在 EC2 上跑（deploy/osrm.md）。本機與備援改用內建步行圖 `app/spatial/walking.py`（OSM 全部 highway 線段建圖，Dijkstra；金山 18,880 段 0.25 秒建圖），量測方式仍記 walking、`provenance.router = osm_graph`，說明寫「內建步行路網（OSM）」（沒設 OSRM 不另註明）；三者順序 OSRM → 內建圖 → 直線×1.3。真實資料驗證：比準地到金山國小 114 m、金山第一市場 89 m、中山溫泉公園 201 m、金山區公所站 168 m，與範本 150/30/190/80 同級距。

## C. 政府資料集下載與進庫（逐步）

目標檔：`data/poi_osm_jinshan.sqlite`（POI 庫）。原則：每個來源一列 manifest，`python scripts/build_poi.py --manifest ../data/sources/manifest.json --out ../data/poi_osm_jinshan.sqlite` 會合併進既有庫（同來源同 id 覆寫）。

1. **加油站（已做）**：`curl -L -o data/sources/cpc_gas_stations.csv "http://www3.cpc.com.tw/opendata_d00/webservice/加油站服務資訊.csv"`，manifest 已有一列（欄位 站名／經度／緯度／站代號）。金山站 (121.6336, 25.2247) 已進庫。
2. **OSM 全類別（已做）**：`python scripts/build_poi.py --overpass "25.20,121.60,25.26,121.68" --out ../data/poi_osm_jinshan.sqlite`。換案子只要改 bbox（south,west,north,east）。
3. **學校**：data.gov.tw 搜「全國各級學校基本資料」（教育部）→ 下載 CSV → 看欄位名（通常「學校名稱」「經度」「緯度」或「Lon」「Lat」）→ manifest 加 `{"type":"school","format":"csv","file":"schools.csv","name":"學校名稱","lon":"經度","lat":"緯度","source":"教育部全國各級學校基本資料"}`。若只有地址沒座標，先跳過（OSM 已有 6 所）。
4. **公有零售市場**：data.gov.tw 搜「公有零售市場」（經濟部商業發展署）→ 同法，type `traditional_market`。
5. **公園**：data.ntpc.gov.tw 搜「公園」（新北市景觀處）→ 常是 CSV 含 X/Y（TWD97 公尺）或經緯度；若是 TWD97，先用 `pyproj` 轉 WGS84 再進 manifest（我可以寫轉檔小腳本）。
6. **殯葬設施**：內政部全國殯葬資訊入口網沒有座標開放檔 → 用人工標定（A-3）。
7. **環境部設施（焚化爐、掩埋場、污水廠、列管污染源）**：data.gov.tw 搜「焚化廠」「掩埋場」「列管事業」→ 多數有 TWD97 或經緯度 → manifest，type 依 facility_measurement.json（incinerator / landfill / sewage_plant / pollution_source）。
8. **金融機構**：data.gov.tw 搜「金融機構基本資料」（金管會）多為地址；中華郵政「郵局據點」有座標 → type `post_office_bank`。銀行分行 OSM 已有 4 筆。
9. **TDX（要 key）**：站牌 `https://tdx.transportdata.tw/api/basic/v2/Bus/Stop/City/NewTaipei?$format=JSON`、客運站 `…/v2/Bus/Station/InterCity`、停車場 `…/v1/Parking/OffStreet/CarPark/City/NewTaipei`、景點 `…/v2/Tourism/ScenicSpot/NewTaipei`；取得 token 後另存 GeoJSON 進 manifest。
10. **都市計畫使用分區（已做）**：城鄉局 78 MB shapefile 已裁金山成 `data/zoning/jinshan_zoning.geojson`；換案子用 `python - <<…` 重新裁（見 docs/05）。
11. **公告土地現值（已做）**：`data/sources/ntpc_land_value_jinshan_113.csv`；換行政區改 `district` 過濾。

每次進庫後 `GET /api/spatial/status` 看各類筆數；`python scripts/check_jinshan_realdata.py ../data/poi_osm_jinshan.sqlite` 看與範本的差距。

## D. 資料授權標示（要放進簡報與系統頁腳）

- 政府資料開放授權條款第 1 版：標示來源機關與資料集名稱（POI.source 已帶）。
- OpenStreetMap：© OpenStreetMap contributors，ODbL；OSM 衍生資料庫若對外散布須同授權。
- 國土測繪中心 WMTS／WMS：免申請，標示「© 國土測繪中心」。
- 人工標定：標「人工標定（來源：現勘／估價師）」。
