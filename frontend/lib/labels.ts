/* 使用者看得到的欄位名稱：操作紀錄差異、裁決鍵、地圖彈窗都用這裡對照，不讓 snake_case 外漏。 */
export const FIELD_ZH: Record<string, string> = {
  case_no: "案號", valuation_date: "估價基準日", district: "鄉鎮市區", land_use: "用地別", appraiser: "不動產估價師", fill_date: "填寫日期", notes: "備註",
  parcel_id: "地號", address: "地址", section_id: "區段編號", range_desc: "區段範圍", survey_date: "勘查日期", geometry: "界線", geometry_source: "界線來源", address_estimate: "依門牌路段推定",
  area_m2: "面積", width_m: "寬度", depth_m: "深度", shape: "形狀", frontage: "臨街情形", terrain: "地勢", road_type: "道路種類", front_road: "面前道路", name: "名稱", width: "寬度",
  school: "接近學校", market: "接近市場", park: "接近公園、廣場", station: "接近車站", commercial_district: "接近商圈", nuisance: "嫌惡設施", street_parking: "停車方便性",
  zoning: "使用分區", bcr_pct: "建蔽率", far_pct: "容積率", building_restricted: "禁限建", other: "其他",
  normal_unit_price: "土地正常單價", transaction_date: "交易日期", date_adjustment: "期日調整", pct: "調整率", index_at_valuation: "基準日指數", index_at_transaction: "交易日指數",
  weight_pct: "權重", comp_no: "比較標的編號", source: "來源", price_total: "總價", building_cost: "建物成本價格", selection: "選取依據",
  survey: "勘查表", land_control: "土地使用管制", transport: "交通運輸", natural: "自然條件", public: "公共建設", special: "特殊設施", pollution: "環境污染", commerce: "工商活動",
  urban_plan: "都市計畫內外", bcr: "建蔽率", far: "容積率", building_prohibited: "禁止建築", main_road_width_m: "主要道路寬度", avg_road_width_m: "區段內道路平均寬度",
  major_station: "大型車站", bus_stop: "站牌", interchange: "交流道", road_development: "道路規劃及闢建程度", drainage: "排水之良否",
  tourism: "觀光遊憩設施", parking: "停車場地", utility: "電業及公用氣體燃料設施", funeral: "殯葬設施", waste: "廢棄物處理設施",
  department_store: "百貨公司", bank: "金融機構", entertainment: "娛樂設施", hotel: "大型展示中心或觀光飯店", foot_traffic: "顧客通行量", shop_ratio_pct: "店舖毗連狀態",
  distance_m: "距離", measure: "量測方式", origin: "起點", in_section: "區段內", computed: "系統推算", assumed: "推定",
  subject_parcel: "比準地", comparables: "比較標的", sections: "地價區段", case: "案件", derived: "推定紀錄", status: "狀態",
};
export const MEASURE_ZH: Record<string, string> = { walking: "步行距離", straight: "直線距離", straight_estimated: "直線估算" };
export const ORIGIN_ZH: Record<string, string> = { parcel_centroid: "宗地中心點", parcel_frontage: "臨路邊界", section_boundary: "地價區段邊界", subject_parcel: "比準地" };
export const OWNER_ZH = (o: string) => (o === "subject" ? "比準地" : /^comp/.test(o) ? `比較標的${o.replace(/\D/g, "")}` : /^P/.test(o) ? `區段 ${o}` : o);

/** "comparables[1].normal_unit_price" → "比較標的2／土地正常單價"；"sections.P001-00.survey.transport.avg_road_width_m" → "地價區段 P001-00／勘查表／交通運輸／區段內道路平均寬度" */
export function pathLabel(path: string): string {
  if (!path || path.startsWith("…")) return path;
  const out: string[] = [];
  const toks = path.replace(/\[(\d+)\]/g, ".#$1").split(".");
  for (let i = 0; i < toks.length; i++) {
    const t = toks[i];
    if (t.startsWith("#")) { const n = Number(t.slice(1)); out[out.length - 1] = (toks[i - 1] === "comparables" ? `比較標的${n + 1}` : `${out[out.length - 1]}${n + 1}`); continue; }
    if (toks[i - 1] === "sections") { out.push(`地價區段 ${t}`); continue; }
    if (/^\d+$/.test(t) && toks[i - 1] === "individual") { out.push(`第${t}項`); continue; }
    out.push(FIELD_ZH[t] || t);
  }
  return out.join("／");
}

/** 裁決鍵 → 中文位置："5:1:R03" → "影響地價區域因素分析明細表 比較標的1 R03"；"loc:表4:比較標的" → "比較法調查估價表 比較標的" */
export function decisionKeyLabel(k: string): string {
  const T: Record<string, string> = { "5": "影響地價區域因素分析明細表", "4": "比較法調查估價表", 表5: "影響地價區域因素分析明細表", 表4: "比較法調查估價表", 表1: "地價區段勘查表" };
  const m = k.match(/^([45]):(\d*):(.+)$/);
  if (m) return `${T[m[1]]}${m[2] ? ` 比較標的${m[2]}` : ""} ${m[1] === "4" ? `第${m[3]}項` : m[3]}`;
  const l = k.match(/^loc:([^:]+):(.+)$/);
  if (l) return `${T[l[1]] || l[1]} ${l[2]}`;
  return k;
}
