# frontend

Next.js 16（App Router、TypeScript、Tailwind 4）、Leaflet + 國土測繪中心 WMTS（EMAP／LANDSECT）。
所有資料走後端 REST（`/api/*` 由 `next.config.ts` rewrites 代理到 `BACKEND_URL`）；不用 Supabase；案件資料存後端（`/api/cases`），前端不做 localStorage 持久化。

```bash
npm install
npm run build && BACKEND_URL=http://127.0.0.1:8000 npx next start -p 3000   # 本機驗收用這個（見下方已知問題）
npm run start:standalone                                                   # Docker 內用：node .next/standalone/server.js
BACKEND_URL=http://127.0.0.1:8000 npm run dev                              # 開發模式（HMR）
```

**開發模式（2026-09-07 更新）**：`BACKEND_URL=http://127.0.0.1:8000 npx next dev -p 3001` 在這台機器已可正常 hydrate（Turbopack，Next 16.3.4）。
先前「dev 頁面不會 hydrate」的現象在改用與生產版不同的埠（3001）後未再出現；判斷是同一個 origin（localhost:3000）先後跑過 `next start` 與 `next dev`，
瀏覽器沿用了舊的 chunk 快取。**慣例：生產版驗收用 3000，開發用 3001，不要在同一埠交替。** 若再遇到，開無痕視窗或清 localhost 的快取即可。
`BACKEND_URL` 在 build 時寫進 rewrites，換後端位址要重 build（compose 用 build arg）。

版面：左側側邊欄依作業流程分四段（① 輸入資料 → ② 產出書表 → ③ 審查 → ④ 輸出），每頁頂端有流程導覽列，頁首標明「這一頁的輸入／產出」與下一步。書表一律用法定全名。
**地價區段勘查表是產出**：當天可能只拿到年期、區段編號、區段範圍，其餘由系統依分區圖、路網、設施資料庫推算，不能推的標「需人工填載」。

| 路徑 | 頁面 | 說明 |
|---|---|---|
| `/` | 案件總覽 | 上傳送審書表（先預覽辨識結果再建案）、開啟案件（進 ① 基本資料）、範例、案件管理 |
| `/input?tab=case\|parcels\|rules` | ① 輸入資料 | 三個分頁：基本資料（區段範圍、比準地位置）、宗地條件與買賣實例、評價基準明細表（進階）；主鍵「儲存並重新產生書表」 |
| `/sheets` | ② 產出書表 | 六頁書表預覽（照《查估書表範本》），下載 Excel／PDF、列印；審查對照檢視連到 `/table1`、`/tables?tab=5|4`、`/map` |
| `/review` | ③ 審查 | 逐項比對、承辦裁決（主鍵「儲存裁決」）、狀態、操作紀錄；意見書在 `/report` |
| `/export` | ④ 輸出 | 「下載全部（zip）」＝Excel＋PDF＋意見書＋三張 PNG；圖說互動地圖在 `/map` |

每頁頂端有案件列（狀態、輸入最後修改／產出最後產生、重新產生書表、另存為新案件、重置案件）。輸入改動後產出標「已過期」並停用下載，按「重新產生書表」即可。
