"use client";
import Link from "next/link";
import { Badge, Card } from "@/components/ui";

/* 操作教學：側邊欄「操作教學」。靜態內容，按鈕與用詞要跟各頁實際文字一致（改介面文字時一併改這裡）。 */

const TOC: [string, string][] = [
  ["before", "開始之前"],
  ["flow", "整體流程"],
  ["a", "情境一：審查送審書表"],
  ["b", "情境二：只有地號，依地號建案"],
  ["c", "情境三：用範例看一遍"],
  ["terms", "顏色與用詞"],
  ["manage", "案件管理"],
  ["faq", "常見問題"],
];

function Steps({ items }: { items: React.ReactNode[] }) {
  return (
    <ol className="space-y-2">
      {items.map((it, i) => (
        <li key={i} className="flex gap-3 text-sm leading-relaxed">
          <span className="shrink-0 w-6 h-6 rounded-full bg-[#ea580c] text-white text-xs flex items-center justify-center mt-0.5">{i + 1}</span>
          <div className="min-w-0">{it}</div>
        </li>
      ))}
    </ol>
  );
}

const K = ({ children }: { children: React.ReactNode }) => <span className="inline-block rounded border border-orange-300 bg-orange-50 text-orange-900 px-1.5 py-0 text-[13px] whitespace-nowrap">{children}</span>;

export default function Guide() {
  return (
    <div className="max-w-5xl">
      <div className="mb-4">
        <h1 className="text-xl font-semibold leading-tight">操作教學</h1>
        <p className="text-sm text-slate-600 mt-1">第一次使用請照「開始之前」→「整體流程」看一遍，再依手上的資料選一種情境照著做。</p>
      </div>

      <nav className="mb-5 flex flex-wrap gap-2 no-print">
        {TOC.map(([id, t]) => <a key={id} href={`#${id}`} className="text-xs px-2.5 py-1 rounded-full border border-orange-200 bg-white hover:bg-orange-50">{t}</a>)}
      </nav>

      <Card title={<span id="before">開始之前</span>}>
        <Steps items={[
          <>在左下角「操作身分」填好姓名與角色（例如：承辦）。所有操作都會記在案件的操作紀錄，審查意見書的落款也用這裡的名字。</>,
          <>準備好手上的資料。三種狀況都可以開始：
            <ul className="list-disc pl-5 mt-1 text-slate-700">
              <li>有估價單位送來的查估書表 PDF → 看「情境一」</li>
              <li>沒有書表，只有估價基準日與比準地地號 → 看「情境二」</li>
              <li>想先熟悉系統 → 看「情境三」</li>
            </ul>
          </>,
          <>本系統的等級、修正率與價格都由規則引擎依查估辦法與作業手冊計算，每一格都能對回評價基準明細表；AI（語言模型）只用在掃描件辨識與意見書文字潤飾，不參與數字。</>,
        ]} />
      </Card>

      <Card title={<span id="flow">整體流程</span>} lead="側邊欄由上而下就是辦案順序；某一段完成後，側邊欄該項會出現 ✓。">
        <div className="grid md:grid-cols-5 gap-2 text-sm">
          {[
            ["案件總覽", "新增或開啟案件；看各案的審查進度與下一步"],
            ["① 輸入資料", "核對評價基準明細表、案件與地價區段、宗地條件與買賣實例"],
            ["② 產出書表", "系統重算全部書表，照範本版面預覽；可看互動地圖"],
            ["③ 審查", "逐格比對填載值與核算值；對不符項做承辦裁決，產生審查意見書"],
            ["④ 輸出", "下載書表 Excel／PDF、審查意見書 Word／PDF、圖說、地政局正式範本"],
          ].map(([t, d], i) => (
            <div key={t} className="rounded-lg border border-orange-200 bg-orange-50/50 p-3">
              <div className="font-semibold">{t}</div>
              <div className="text-xs text-slate-600 mt-1">{d}</div>
              {i < 4 && <div className="hidden md:block text-right text-orange-400 text-xs mt-1">→</div>}
            </div>
          ))}
        </div>
        <p className="text-xs text-slate-600 mt-3">開啟案件後，每一頁右上角都有「下一步」按鈕，照著按就會走完整個流程；頁面標題下的「說明 ▸」可展開該頁的輸入與產出。</p>
      </Card>

      <Card title={<span id="a">情境一：審查估價單位送來的查估書表</span>}>
        <Steps items={[
          <>到「案件總覽」按 <K>＋ 新增案件</K>，選 <K>上傳輸入檔</K>。</>,
          <>把送審書表 PDF 拖進框內（整份或拆成勘查表／表5／表4 都可以，也能一起放宗地清冊、買賣實例 xlsx、評價基準明細表、地籍圖、地價區段圖）。系統會逐份顯示辨識結果，先確認案號、比準地、缺漏與低信心欄位。</>,
          <>按 <K>建立一個案件並開始審查 →</K>。</>,
          <>到「① 輸入資料」的「評價基準明細表」分頁，確認用的是該地區、該用地別的基準表；再看「案件與地價區段」「宗地條件與買賣實例」是否抽對。有改動就按 <K>儲存並重新產生書表</K>。</>,
          <>到「③ 審查」看結果：每一列有「估價單位填載／系統核算／說明／依據」。按 <K>看基準表格位 →</K> 可看該項在基準表的判定條件與修正百分比矩陣。</>,
          <>對每一項 <Badge kind="error">不符</Badge> 在「承辦裁決」選 <K>接受填載</K>（經審酌採估價單位之值，請填說明）或 <K>維持不符</K>（請估價單位補正），按 <K>儲存裁決</K>。</>,
          <>按右上「下一步：審查意見書」，檢查結論與逐條意見（含審查重點條號、法源與承辦裁決）。</>,
          <>到「④ 輸出」下載審查意見書 Word／PDF 與重算後的書表；或按 <K>下載全部</K> 一次打包。</>,
        ]} />
      </Card>

      <Card title={<span id="b">情境二：沒有書表，只有年期與地號</span>} lead="適合徵收案剛開始、還沒有估價單位書表時，讓系統先產出一版供估價師修改。">
        <Steps items={[
          <>到「案件總覽」按 <K>＋ 新增案件</K>，選 <K>依地號建案</K>。</>,
          <>填案號、估價基準日（例 1140901）、鄉鎮市區、用地別，以及比準地地號（例：金美段489地號）。沒有地號時改填「區段範圍」四至文字，系統會圍出區段並依查估辦法 §18 自動選比準地。</>,
          <>保持勾選「建立後立即依地號產生」，按 <K>建立並產生 →</K>。約 30 秒，系統依序做：地籍界線 → 宗地屬性 → 區段範圍 → 勘查表 → 設施距離 → 實價登錄比較標的。</>,
          <>完成後會看到「填寫結果清單」：哪些欄位來自資料、哪些是量測、哪些是推定、哪些仍空白。標「推定」的值請逐項確認，空白的欄位請人工填入。</>,
          <>地籍界線找不到時，到「① 輸入資料」→「案件與地價區段」按 <K>⬆ 匯入地籍圖</K>（GeoJSON、KML、GML 或 Shapefile zip），再按 <K>依地號產生</K>。</>,
          <>到「② 產出書表」預覽，到「④ 輸出」下載。此情境沒有送審書表可比對，「③ 審查」只會列出資料缺口與需確認項。</>,
        ]} />
      </Card>

      <Card title={<span id="c">情境三：用範例看一遍</span>}>
        <p className="text-sm mb-2">到「案件總覽」按 <K>＋ 新增案件</K> → <K>載入範例</K>，挑一個：</p>
        <ul className="text-sm space-y-1.5 list-disc pl-5">
          <li><b>範例一：金山區 P002-00 地價區段</b>：送審書表填載與系統核算相符，先看正常的樣子。</li>
          <li><b>範例二：含填載錯誤之送審書表</b>：同一案但等級與修正率抄錯，練習不符項、承辦裁決與意見書。</li>
          <li><b>範例三：僅有年期、區段編號、區段範圍之勘查表</b>：看系統如何由圖資推算勘查表其餘欄位。</li>
          <li><b>範例四：樹林區普通住宅用地</b>：四個區段、三個比較標的，可輸出地政局正式範本書表。</li>
        </ul>
        <p className="text-xs text-slate-600 mt-2">建議順序：範例一 → 範例二（練裁決）→ 範例四。</p>
      </Card>

      <Card title={<span id="terms">顏色與用詞</span>}>
        <table className="w-full text-sm">
          <tbody className="[&_td]:py-2 [&_td]:pr-3 [&_td]:align-top [&_tr]:border-t [&_tr]:border-slate-100">
            <tr><td className="w-28"><Badge kind="ok">相符</Badge></td><td>填載值與系統核算一致。</td></tr>
            <tr><td><Badge kind="error">不符</Badge></td><td>估價單位填載值與系統依基準明細表核算之值不同，需要承辦裁決。</td></tr>
            <tr><td><Badge kind="warn">需確認</Badge></td><td>作業手冊未明定、依範本或資料推定的事項，<b>不判為錯誤</b>，請估價單位於備註敘明或承辦確認。</td></tr>
            <tr><td><Badge kind="info">備註</Badge></td><td>提醒事項，不影響結論。</td></tr>
            <tr><td><span className="inline-block border rounded px-1.5 py-0.5 text-xs bg-amber-50 text-amber-900 border-amber-300">需人工確認</span></td><td>系統判定不足（勘查事實缺漏或基準表沒有對應項目），請人工判定等級。</td></tr>
            <tr><td><span className="inline-block border rounded px-1.5 py-0.5 text-xs bg-red-50 text-red-800 border-red-300">需人工填載</span></td><td>欄位空白，屬實地勘查或都市計畫書事項（建蔽率、路寬、排水、地勢等），系統不推測，請人工填入。</td></tr>
            <tr><td>推定</td><td>系統依圖資或資料推算的值，會標示來源；估價師或承辦填的值永遠優先。</td></tr>
            <tr><td>承辦裁決</td><td>對不符項的處置：<b>接受填載</b>＝經審酌採估價單位之填載；<b>維持不符</b>＝請估價單位補正。裁決與說明會寫進審查意見書與操作紀錄。</td></tr>
          </tbody>
        </table>
      </Card>

      <Card title={<span id="manage">案件管理</span>}>
        <ul className="text-sm space-y-1.5 list-disc pl-5">
          <li><b>狀態</b>：案件分為草稿、審查中、已完成，在案件列切換。案件總覽的「下一步」欄會依各案現況提示該做什麼。</li>
          <li><b>產出已過期</b>：改過輸入後，產出頁會淡化並停用下載，按 <K>儲存並重新產生書表</K> 即恢復。</li>
          <li><b>重置案件</b>：在案件列按 <K>重置案件…</K>，可選「回到原始輸入」（回到建案時的資料）或 <K>清空重填</K>（只留基本資料、區段編號與已匯入的圖檔）。</li>
          <li><b>封存</b>：從清單隱藏，資料與紀錄保留；在案件總覽勾「已封存」可復原。</li>
          <li><b>操作紀錄</b>：誰在什麼時候做了什麼，都記在案件的操作紀錄，可追溯。</li>
        </ul>
      </Card>

      <Card title={<span id="faq">常見問題</span>}>
        <dl className="text-sm space-y-3">
          {[
            ["數字會不會是 AI 算的？", "不會。等級、修正率、價格全由規則引擎依查估辦法與作業手冊計算，每一格都能點回法源與基準表格位。"],
            ["推定值錯了怎麼辦？", "推定值只標「需確認」、不判錯。直接在「① 輸入資料」改成正確值，按「儲存並重新產生書表」即可，人工填的值優先。"],
            ["地籍界線找不到？", "到「① 輸入資料」匯入地籍圖檔（GeoJSON、KML、GML 或 Shapefile zip），或在地圖上點選比準地位置。"],
            ["基準日前的實價登錄不夠？", "系統會依查估辦法 §17、§19 逐步放寬並標明理由；仍不足時列為人工填寫。"],
            ["地圖空白？", "底圖由國土測繪中心線上提供，網路不通時地圖會空白，但計算與書表不受影響。"],
            ["要列印書表？", "請到「② 產出書表」下載完整書表 PDF 再列印（表 A4、圖 A3 橫式），不要用瀏覽器直接列印網頁。"],
          ].map(([q, a]) => (
            <div key={q}>
              <dt className="font-semibold">{q}</dt>
              <dd className="text-slate-700 mt-0.5">{a}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-slate-600 mt-4">資料來源（圖資、法規、服務清單）請看側邊欄 <Link href="/sources" className="underline hover:text-[#c2410c]">資料來源</Link>。</p>
      </Card>
    </div>
  );
}
