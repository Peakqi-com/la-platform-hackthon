# 03 內部 Schema

原則：**input adapter 把任何當天格式轉成這個；後面所有模組只認這個。** 完整範例見 `fixtures/sample_case_P002-00.json`。

## Case

```jsonc
{
  "case_no": "1140901-99-001",
  "valuation_date": "1140901",           // 估價基準日（民國）
  "district": "新北市金山區",
  "land_use": "商業用地",                 // 住宅|商業|工業|農業|其他 → 決定用哪張表5與基準表
  "rulesets": { "regional": "<rules id>", "individual": "<rules id>" }
}
```

## Section（地價區段）= 表1 勘查表

```jsonc
{
  "section_id": "P002-00",
  "geometry": <GeoJSON Polygon, TWD97 或 WGS84，可缺>,
  "range_desc": "北側至…",
  "survey_date": "114-09-18",
  "survey": {
    "land_control": { "urban_plan": "都市計畫內", "zoning": "第二種商業區", "bcr": 70, "far": 240,
                      "building_prohibited": false, "building_restricted": false },
    "transport":    { "main_road_width_m": {"name":"中山路","value":18}, "avg_road_width_m": {"value":12},
                      "major_station": [Facility], "bus_stop": [Facility], "interchange": [Facility],
                      "road_development": "已完全開發" },
    "natural":      { "drainage": "有排水系統不易淹水", "terrain": "該區地勢平坦" },
    "public":       { "market": [Facility], "park": [Facility], "tourism": [Facility], "parking": [Facility] },
    "special":      { "utility": [Facility], "funeral": [Facility], "waste": [Facility] },
    "pollution":    { "source": [Facility] },
    "commerce":     { "department_store": [Facility], "bank": [Facility], "entertainment": [Facility],
                      "hotel": [Facility], "foot_traffic": "顧客通行量多", "shop_ratio_pct": 90 },
    "other": null
  }
}
```

`survey.*` 的路徑就是 `rules/*_regional.json` 每條 rule 的 `survey_field`。住宅用地會多 `public.school`、`public.service`、`natural.sunlight/view/slope`、`improvement.*`——加規則時同步加欄位即可，引擎不改。

## Facility（設施觀測）

```jsonc
{
  "name": "金山第1公墓",
  "type": "cemetery",                     // rules/facility_measurement.json 的 key
  "in_section": false,                    // 區段內有 → 勘查表「本區段內」
  "distance_m": 80,
  "measure": "straight",                  // straight | walking   ← 必填（推算時由設定檔決定，人工填入時要問）
  "origin": "section_boundary",           // section_boundary | subject_parcel | parcel_centroid | parcel_frontage
  "source": "內政部殯葬設施資料",           // 資料來源；人工填入 = "manual"；從估價師書表抄來 = "表1 地價區段勘查表（估價師填）"
  "assumed": true,                        // 可缺；adapter 從書表/清冊抄距離時 measure/origin 是帶預設的推定 → UI 標「需確認」
  "geometry": <GeoJSON Point/Polygon，可缺>
}
```

## Parcel（宗地）= 表7 清冊一列 = 表4 一欄

```jsonc
{
  "parcel_id": "金美段489地號", "address": "...", "section_id": "P002-00",
  "geometry": <GeoJSON Polygon，可缺>,
  "area_m2": 113.21, "width_m": 5, "depth_m": 23,
  "shape": "方形", "frontage": "單面臨街", "terrain": "平坦",
  "road_type": "主要道路", "front_road": {"name":"中山路","width_m":18},
  "school": Facility, "market": Facility, "park": Facility, "station": Facility, "commercial_district": Facility,
  "nuisance": [Facility],
  "street_parking": "可路邊停車",
  "zoning": "第二種商業區", "bcr_pct": 70, "far_pct": 240, "building_restricted": false,
  "other": null                           // 免修正 → null；表4 顯示「-」
}
```

欄位名 = `rules/*_individual.json` 的 `parcel_field`。item_no 7–25 對應清冊/表4 欄位編號。

## Comparable（比較標的）= Parcel + 交易資料

```jsonc
{ ...Parcel,
  "comp_no": 1, "normal_unit_price": 184763, "transaction_date": "114.05.28",
  "date_adjustment": { "pct": 2.00, "index_at_valuation": 48481, "index_at_transaction": 47513, "note": "..." },
  "weight_pct": 100,                      // 可缺 → 引擎依排名給預設
  "source": { "lvr_id": "...", "price_total": ..., "note": "實價登錄比對用" }
}
```

## AdapterResult（所有 input adapter 的回傳）

```jsonc
{ "kind": "parcels|comparables|rules_table|pdf_forms",
  "data": {...},                    // parcels: {parcels[], meta} / comparables: {comparables[], meta} /
                                    // rules_table: {rulesets{regional, individual}, long_rows[], meta} /
                                    // pdf_forms: {case, sections, subject_parcel, comparables, submitted{table1,table5,table4}, pages[]}
  "missing_fields": ["parcels[1].width_m"],   // 缺欄位路徑；「-」明示免填不算缺
  "warnings": ["..."],              // 推定、疑點、被正規化的值、低信心欄位
  "confidence": {"path": 0.9} }     // 文字層/Excel = 1.0；vision 抽取 = 模型自報
```

基準明細表的 canonical 交換格式（CSV/xlsx，`fixtures/jinshan_commercial_rules_table.csv`）：一列 = 一個細項的一個比準地等級，
欄 `scope, group_name, item_no, item_name, level, condition, pct_優, pct_稍優, pct_普通, pct_稍劣, pct_劣, note`；`pct_X` = 比較標的等級為 X 時的修正率。

## 引擎輸出

- `Table5`：rows[{rule_id, name, subject_level, comparable_level, subject_num, comparable_num, pct, issues}], group_subtotals, total_pct
- `Table4`：comparables[{comp_no, date_adjustment_pct, price_at_valuation_date, regional_adjustment_pct, rows[{item_no, subject_value, comparable_value, levels, pct|null}], individual_total_pct, abs_sum_pct, similarity, weight_pct, trial_price}], subject_comparison_price
- `Finding`：{severity: error|warn|info, checklist: "vi"|"vii"|..., table, location, submitted, computed, message, basis}

## Submitted（審查模式的輸入 = 估價師填的表，抽取後）

見 `backend/app/engine/verify.py` docstring。抽取器（Excel/PDF）的目標就是產出這個結構。

## 規則 JSON（`rules/*_regional.json`, `*_individual.json`）

```jsonc
{ "id": "...", "land_use": "商業用地", "scope": "regional|individual", "groups": [...],
  "rules": [{
    "id": "R2-1", "item_no": 14, "group": 2, "name": "...",
    "levels": ["優","稍優","普通","稍劣","劣"],   // 由優到劣；2/3/5 級皆可
    "max_pct": 10,                               // 修正率 = (比較標的索引 − 比準地索引) × max/(n−1)
    "matrix": {...},                             // 可選：非等距時放完整矩陣
    "criteria": { "type": "enum|boolean|bands|distance|manual", ... },
    "survey_field" | "parcel_field": "...",     // 觀測值在 Section.survey / Parcel 裡的路徑
    "facility_types": [...],                     // distance 類：對應 facility_measurement.json
    "note": "推定或疑點"
  }]
}
```

criteria 型別：
- `enum`: `map{value→level}`, `normalize{alias→value}`, `default`
- `boolean`: `true_level`, `false_level`
- `bands`: `bands[{level,min?,max?}]`（min 含 max 不含）, `none_level`
- `distance`: 同 bands + `in_section_level`, `none_level`, `direction: farther_is_better`, `aggregate: worst`；觀測值為 Facility 或 [Facility]，取最近者
- `manual`: 引擎不判，估價師自填
