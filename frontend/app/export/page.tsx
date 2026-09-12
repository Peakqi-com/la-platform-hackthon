"use client";
import { useState } from "react";
import Link from "next/link";
import { useCase } from "@/components/CaseContext";
import { StaleBanner } from "@/components/Stale";
import PageHeader from "@/components/PageHeader";
import { Btn, Card, Empty } from "@/components/ui";
import { actorHeaders, Any, getActor, zhError } from "@/lib/api";

/* ④ 輸出：同一份內容一列，格式不同只在「下載」欄分開按鈕；最上面一鍵打包。所有下載都經 fetch 帶操作身分，寫入操作紀錄。 */
type Fmt = { key: string; fmt: string; url: (id: string) => string; file: (no: string) => string };
type Item = { key: string; name: string; desc: string; formats: Fmt[]; needOutputs?: boolean };

const reportQuery = () => { const a = getActor(); return `?reviewer=${encodeURIComponent(a.name)}&reviewer_role=${encodeURIComponent(a.role)}`; };
const ITEMS: Item[] = [
  { key: "sheets", name: "查估書表", desc: "六頁：地價區段勘查表、影響地價區域因素分析明細表、比較法調查估價表、地價區段略圖、地價使用分區圖、地價區段圖（Excel 為六張工作表，PDF 照範本頁序）", needOutputs: true,
    formats: [{ key: "xlsx", fmt: "Excel", url: (id) => `/api/cases/${id}/sheets.xlsx`, file: (no) => `${no}_查估書表.xlsx` }, { key: "pdf", fmt: "PDF", url: (id) => `/api/cases/${id}/sheets.pdf`, file: (no) => `${no}_查估書表.pdf` }] },
  { key: "report", name: "審查意見書", desc: "逐條意見含審查重點條號、法源與承辦裁決，附三張圖說；落款為操作身分", needOutputs: true,
    formats: [{ key: "docx", fmt: "Word", url: (id) => `/api/cases/${id}/report.docx${reportQuery()}`, file: (no) => `${no}_審查意見書.docx` }, { key: "rpdf", fmt: "PDF", url: (id) => `/api/cases/${id}/report.pdf${reportQuery()}`, file: (no) => `${no}_審查意見書.pdf` }] },
  { key: "sketch", name: "地價區段略圖", desc: "區段範圍、宗地位置、道路、段籍圖底圖，含比例尺與簽章欄", needOutputs: true, formats: [{ key: "sketch", fmt: "PNG", url: (id) => `/api/cases/${id}/map.png?mode=sketch`, file: (no) => `${no}_地價區段略圖.png` }] },
  { key: "zoning", name: "地價使用分區圖", desc: "使用分區色塊與區段範圍", needOutputs: true, formats: [{ key: "zoning", fmt: "PNG", url: (id) => `/api/cases/${id}/map.png?mode=zoning`, file: (no) => `${no}_地價使用分區圖.png` }] },
  { key: "section", name: "地價區段圖", desc: "區段範圍、宗地、設施位置與量測路線", needOutputs: true, formats: [{ key: "section", fmt: "PNG", url: (id) => `/api/cases/${id}/map.png?mode=section`, file: (no) => `${no}_地價區段圖.png` }] },
  { key: "official", name: "地政局正式範本書表", desc: "直接填入地政局 Excel 範本：地價區段勘查表（每區段一張工作表）、影響地價區域因素分析明細表（住宅用地版面）、比較法調查估價表；格線與版面與範本相同", needOutputs: true,
    formats: [{ key: "ot3", fmt: "勘查表", url: (id) => `/api/cases/${id}/official/t3.xlsx`, file: (no) => `${no}_表3_地價區段勘查表.xlsx` }, { key: "ot5", fmt: "區域因素表", url: (id) => `/api/cases/${id}/official/t5.xlsx`, file: (no) => `${no}_表5-1_影響地價區域因素分析明細表.xlsx` }, { key: "ot4", fmt: "比較法估價表", url: (id) => `/api/cases/${id}/official/t4.xlsx`, file: (no) => `${no}_表4_比較法調查估價表.xlsx` }, { key: "ozip", fmt: "三份 zip", url: (id) => `/api/cases/${id}/official.zip`, file: (no) => `${no}_正式範本書表.zip` }] },
  { key: "parcels", name: "宗地個別因素清冊", desc: "本案比準地與比較標的的個別因素（清冊版面），可填後再匯入", formats: [{ key: "parcels", fmt: "Excel", url: (id) => `/api/cases/${id}/parcels.xlsx`, file: (no) => `${no}_宗地個別因素清冊.xlsx` }] },
  { key: "comps", name: "買賣實例", desc: "比較標的交易資料，可填後再匯入", formats: [{ key: "comps", fmt: "Excel", url: (id) => `/api/cases/${id}/comparables.xlsx`, file: (no) => `${no}_買賣實例.xlsx` }] },
];

export default function Export() {
  const { rec, stale } = useCase();
  const [busy, setBusy] = useState<string | null>(null);
  const [msg, setMsg] = useState<Record<string, string>>({});
  if (!rec) return <Empty />;
  const no = rec.data.case.case_no || "case";
  async function dl(key: string, url: string, filename: string) {
    setBusy(key); setMsg((m) => ({ ...m, [key]: "" }));
    try {
      const r = await fetch(url, { headers: actorHeaders() });
      if (!r.ok) throw new Error(zhError(r.status, await r.json().catch(() => null)));
      const blob = await r.blob(); const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = filename; a.click();
      setMsg((m) => ({ ...m, [key]: `已下載 ${filename}` }));
    } catch (e: Any) { setMsg((m) => ({ ...m, [key]: String(e.message || e) })); } finally { setBusy(null); }
  }
  return (
    <div>
      <PageHeader title="④ 輸出" desc="每個檔案可個別下載，或一次打包成 zip。" next={{ href: "/", label: "案件總覽", plain: true }} />
      <StaleBanner what="輸出" />
      <Card title="全部打包" hint="查估書表 Excel 與 PDF、審查意見書 Word 與 PDF、三張圖說 PNG，一個 zip。" right={<Btn onClick={() => dl("zip", `/api/cases/${encodeURIComponent(rec.id)}/bundle.zip?reviewer=${encodeURIComponent(getActor().name)}&reviewer_role=${encodeURIComponent(getActor().role)}`, `${no}_全部輸出.zip`)} disabled={stale || !!busy} busy={busy === "zip"} title={stale ? "產出已過期，請先重新產生書表" : undefined}>⬇ 下載全部（zip）</Btn>}>
        {msg.zip && <div className="text-xs text-slate-600">{msg.zip}</div>}
        <div className="text-xs text-slate-500">簽章欄：{rec.data.case.appraiser || "（未填）"}；填寫日期：{rec.data.case.fill_date || "（未填）"}；意見書落款：{getActor().name || "（未填操作身分）"}。</div>
      </Card>
      <Card title="個別檔案">
        <div className="overflow-x-auto"><table className="grid"><thead><tr><th>檔案</th><th>內容</th><th className="whitespace-nowrap w-1">下載</th></tr></thead>
          <tbody>{ITEMS.map((it) => (
            <tr key={it.key}>
              <td className="whitespace-nowrap font-medium">{it.name}</td>
              <td className="text-sm">{it.desc}{it.formats.map((f) => msg[f.key] && <div key={f.key} className="text-xs text-slate-600 mt-1">{msg[f.key]}</div>)}</td>
              <td className="whitespace-nowrap"><div className="flex gap-2">{it.formats.map((f) => <Btn key={f.key} kind="ghost" onClick={() => dl(f.key, f.url(encodeURIComponent(rec.id)), f.file(no))} disabled={(it.needOutputs && stale) || !!busy} busy={busy === f.key} title={it.needOutputs && stale ? "產出已過期，請先重新產生書表" : `下載 ${f.file(no)}`}>⬇ {f.fmt}</Btn>)}</div></td>
            </tr>))}</tbody></table></div>
        <div className="text-xs text-slate-500 mt-2">意見書也可到 <Link className="underline" href={`/report?case=${encodeURIComponent(rec.id)}`}>審查意見書</Link> 頁預覽後下載；地圖可在 <Link className="underline" href={`/map?case=${encodeURIComponent(rec.id)}`}>地圖（互動檢視）</Link> 檢視。</div>
      </Card>
    </div>
  );
}
