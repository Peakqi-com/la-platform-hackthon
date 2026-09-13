/* docs/05_data_sources.md 的解析：章節（## 一、…）、段落、表格、清單。/sources 頁套版用；文件本身是唯一來源。 */

export type Block =
  | { kind: "p"; text: string }
  | { kind: "table"; headers: string[]; rows: string[][] }
  | { kind: "list"; items: string[] };

export type Section = { id: string; numeral: string | null; title: string; blocks: Block[]; rowCount: number };
export type Doc = { intro: string[]; sections: Section[] };

/* 依 | 切欄，但反引號內的 | 不算（例：`shop=supermarket|mall`） */
function splitCells(line: string): string[] {
  const s = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  const out: string[] = []; let cur = ""; let inCode = false;
  for (const ch of s) {
    if (ch === "`") { inCode = !inCode; cur += ch; continue; }
    if (ch === "|" && !inCode) { out.push(cur.trim()); cur = ""; continue; }
    cur += ch;
  }
  out.push(cur.trim());
  return out;
}

const NUMERAL = /^([一二三四五六七八九十]+)、(.+)$/;

export function parseDoc(md: string): Doc {
  const lines = md.replace(/\r/g, "").split("\n");
  const intro: string[] = [];
  const sections: Section[] = [];
  let cur: Section | null = null;
  let para: string[] = [];
  let i = 0;
  const skipIntro = (t: string) => t.startsWith("狀態記號") || t.includes("claude.ai/");   // 狀態圖例改用篩選鈕；網頁版連結不再需要
  const flushPara = () => {
    if (!para.length) return;
    const text = para.join(" ").trim(); para = [];
    if (!text) return;
    if (cur) cur.blocks.push({ kind: "p", text }); else if (!skipIntro(text)) intro.push(text);
  };
  while (i < lines.length) {
    const ln = lines[i];
    if (/^# /.test(ln)) { i++; continue; }
    const h = /^## (.+)$/.exec(ln);
    if (h) {
      flushPara();
      const m = NUMERAL.exec(h[1].trim());
      cur = { id: `s${sections.length + 1}`, numeral: m ? m[1] : null, title: m ? m[2] : h[1].trim(), blocks: [], rowCount: 0 };
      sections.push(cur); i++; continue;
    }
    if (/^\s*\|/.test(ln)) {
      flushPara();
      const headers = splitCells(ln); i++;
      if (i < lines.length && /^\s*\|[\s:|-]+\|?\s*$/.test(lines[i])) i++;   // 分隔列
      const rows: string[][] = [];
      while (i < lines.length && /^\s*\|/.test(lines[i])) { rows.push(splitCells(lines[i])); i++; }
      if (cur) { cur.blocks.push({ kind: "table", headers, rows }); cur.rowCount += rows.length; }
      continue;
    }
    if (/^\s*- /.test(ln)) {
      flushPara();
      const items: string[] = [];
      while (i < lines.length && /^\s*- /.test(lines[i])) { items.push(lines[i].replace(/^\s*- /, "").trim()); i++; }
      if (cur) cur.blocks.push({ kind: "list", items });
      continue;
    }
    if (!ln.trim()) { flushPara(); i++; continue; }
    para.push(ln.trim()); i++;
  }
  flushPara();
  return { intro, sections };
}

/* 狀態欄：「離線、推定」「線上抓取後離線」「備援、推定」→ 一個個徽章；每個徽章歸到五類之一，篩選用 */
export type StatusKind = "offline" | "online" | "apply" | "inferred" | "fallback" | "other";
export const STATUS_KINDS: { kind: StatusKind; label: string }[] = [
  { kind: "offline", label: "離線" }, { kind: "online", label: "線上" }, { kind: "apply", label: "需申請" }, { kind: "inferred", label: "推定" }, { kind: "fallback", label: "備援" },
];
export function statusKind(token: string): StatusKind {
  if (token.includes("需申請") || token.includes("需地政局") || token.includes("需金鑰") || token.includes("需開通")) return "apply";
  if (token.includes("離線")) return "offline";
  if (token.includes("線上")) return "online";
  if (token.includes("推定")) return "inferred";
  if (token.includes("備援")) return "fallback";
  return "other";
}
export function statusTokens(cell: string): string[] {
  return cell.split(/[、，,]|後(?=離線)/).map((t) => t.trim()).filter(Boolean);
}

/* 名稱欄：「土地徵收補償市價查估辦法 §5、7…」「作業手冊（內政部 104 年 3 月版，169 頁）」→ 標題＋灰字附註 */
export function splitName(cell: string): { title: string; note: string | null } {
  const paren = /^(.*?)（(.+)）\s*$/.exec(cell);
  if (paren) return { title: paren[1].trim(), note: paren[2].trim() };
  const sec = /^(.*?)\s+(§.+)$/.exec(cell);
  if (sec) return { title: sec[1].trim(), note: sec[2].trim() };
  return { title: cell, note: null };
}
