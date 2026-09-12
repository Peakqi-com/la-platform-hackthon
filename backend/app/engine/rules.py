"""
規則引擎核心：把「事實」變成「等級」，把「兩個等級」變成「修正率」。

完全不碰 LLM。所有判斷都可追溯到 rules/*.json 的某一格。

名詞：
- rule      : 基準明細表的一個細項（例如「面前道路寬度」）
- level     : 優/稍優/普通/稍劣/劣（依 rule.levels 排序，index 0 = 最優）
- obs       : 觀測值 —— 數值、字串、布林、或設施清單 [{"name","distance_m","in_section"}]
- adjustment: 比較標的相對於比準地的修正率（%），正值代表比準地條件較佳
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RULES_DIR = Path(__file__).resolve().parents[3] / "rules"


class GradeError(ValueError):
    """事實不足以判等級（缺欄位、enum 對不上…）。呼叫端應把它變成「需人工確認」而不是崩潰。"""


@dataclass
class Rule:
    id: str
    name: str
    group: int
    levels: list[str]
    max_pct: float
    criteria: dict
    item_no: int | None = None
    survey_field: str | None = None
    parcel_field: str | None = None
    facility_types: list[str] = field(default_factory=list)
    note: str | None = None
    explicit_matrix: dict | None = None  # 若基準表不是等距，可放完整矩陣 {subj_level: {comp_level: pct}}

    @property
    def step(self) -> float:
        n = len(self.levels)
        return self.max_pct / (n - 1) if n > 1 else 0.0

    def level_index(self, level: str) -> int:
        try:
            return self.levels.index(level)
        except ValueError as e:
            raise GradeError(f"{self.id} {self.name}: 等級「{level}」不在 {self.levels}") from e

    @property
    def is_manual(self) -> bool:
        return self.criteria.get("type") == "manual"


@dataclass
class RuleSet:
    id: str
    scope: str  # "regional" | "individual"
    land_use: str
    groups: dict[int, str]
    rules: list[Rule]

    def by_id(self, rid: str) -> Rule:
        for r in self.rules:
            if r.id == rid:
                return r
        raise KeyError(rid)

    def by_item_no(self, no: int) -> Rule:
        for r in self.rules:
            if r.item_no == no:
                return r
        raise KeyError(no)


def load_ruleset(name_or_path: str | Path) -> RuleSet:
    p = Path(name_or_path)
    if not p.exists():
        p = RULES_DIR / f"{name_or_path}.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    rules = [
        Rule(
            id=r["id"], name=r["name"], group=r["group"], levels=r["levels"], max_pct=r["max_pct"],
            criteria=r["criteria"], item_no=r.get("item_no"), survey_field=r.get("survey_field"),
            parcel_field=r.get("parcel_field"), facility_types=r.get("facility_types", []),
            note=r.get("note"), explicit_matrix=r.get("matrix"),
        )
        for r in data["rules"]
    ]
    return RuleSet(
        id=data["id"], scope=data["scope"], land_use=data["land_use"],
        groups={g["no"]: g["name"] for g in data["groups"]}, rules=rules,
    )


# ---------------------------------------------------------------- grading

def _num(obs: Any) -> float | None:
    if obs is None:
        return None
    if isinstance(obs, (int, float)):
        return float(obs)
    if isinstance(obs, dict):
        for k in ("value", "width_m", "distance_m"):
            if k in obs and obs[k] is not None:
                return float(obs[k])
        return None
    if isinstance(obs, str):
        s = obs.replace("%", "").replace(",", "").strip()
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _in_bands(bands: list[dict], v: float) -> str | None:
    for b in bands:
        lo, hi = b.get("min"), b.get("max")
        if (lo is None or v >= lo) and (hi is None or v < hi):
            return b["level"]
    return None


def _facility_list(obs: Any) -> list[dict]:
    if obs is None:
        return []
    if isinstance(obs, dict):
        return [obs]
    if isinstance(obs, list):
        return [o for o in obs if o]
    return []


def grade(rule: Rule, obs: Any) -> str | None:
    """把觀測值判成等級。manual 類型回傳 None（由估價師自填）。"""
    c = rule.criteria
    t = c.get("type")

    if t == "manual":
        return None

    if t == "enum":
        if obs is None:
            raise GradeError(f"{rule.id} {rule.name}: 缺少觀測值")
        if isinstance(obs, bool):                                      # 三級「有無限制建築」等：勘查表存布林，基準表條件寫「無」「有」
            obs = "有" if obs else "無"
        elif isinstance(obs, (list, tuple, dict)) and any("項" in k for k in c.get("map", {})):   # 「建築基地改良」：條件是項數，勘查表存勾選清單
            n = sum(1 for v in obs.values() if v) if isinstance(obs, dict) else len(obs)
            obs = "無" if n == 0 else {1: "一項", 2: "二項", 3: "三項"}.get(n, "四項以上")
        key = obs if isinstance(obs, str) else str(obs)
        key = c.get("normalize", {}).get(key, key)
        if key in c["map"]:
            return c["map"][key]
        if "default" in c:
            return c["default"]
        raise GradeError(f"{rule.id} {rule.name}: 「{key}」不在判定條件 {list(c['map'])}")

    if t == "boolean":
        if obs is None:
            raise GradeError(f"{rule.id} {rule.name}: 缺少觀測值")
        if isinstance(obs, str):
            obs = obs.strip() in ("有", "是", "true", "True", "1", "有禁止或限制建築")
        return c["true_level"] if bool(obs) else c["false_level"]

    if t == "bands":
        v = _num(obs)
        if v is None:
            if "none_level" in c:
                return c["none_level"]
            raise GradeError(f"{rule.id} {rule.name}: 缺少數值")
        lv = _in_bands(c["bands"], v)
        if lv is None:
            raise GradeError(f"{rule.id} {rule.name}: 數值 {v} 不在任何級距")
        return lv

    if t == "distance":
        if obs is None:
            # 勘查表／清冊根本沒有這一欄（≠ 填「無」的空清單 []）→ 不能推定為無設施，要人工確認
            raise GradeError(f"{rule.id} {rule.name}: 缺少觀測值（勘查表未填此欄；填「無」請給空清單）")
        fac = _facility_list(obs)
        if not fac:
            if "none_level" in c:
                return c["none_level"]
            raise GradeError(f"{rule.id} {rule.name}: 無設施資料")
        # 區段內有 → 對「愈近愈好」是最優；對「愈遠愈好」(嫌惡) 是最劣
        if any(f.get("in_section") for f in fac) and "in_section_level" in c:
            return c["in_section_level"]
        dists = [_num(f) for f in fac]
        dists = [d for d in dists if d is not None]
        if not dists:
            # 有列設施但沒有距離：不能當「無設施」判 none_level（嫌惡設施會因此得最優），要人工補距離
            raise GradeError(f"{rule.id} {rule.name}: 已列設施但無距離，請補量測或人工確認")
        # 兩種方向都取「最近者」：愈近愈好→最近=最優；愈遠愈好(aggregate=worst)→最近=最劣
        d = min(dists)
        lv = _in_bands(c["bands"], d)
        if lv is None:
            raise GradeError(f"{rule.id} {rule.name}: 距離 {d}m 不在任何級距")
        return lv

    raise GradeError(f"{rule.id}: 未知 criteria type {t}")


# ---------------------------------------------------------------- adjustment

def adjustment(rule: Rule, subject_level: str | None, comparable_level: str | None) -> float | None:
    """
    修正率（%）= (比較標的等級索引 − 比準地等級索引) × step。
    比準地優於比較標的 → 正值（比較標的價格要往上調才等於比準地）。
    任一方為 None（manual 或免修正）→ None。
    """
    if subject_level is None or comparable_level is None:
        return None
    if rule.explicit_matrix:
        return float(rule.explicit_matrix[subject_level][comparable_level])
    return round((rule.level_index(comparable_level) - rule.level_index(subject_level)) * rule.step, 4)


LEVEL_NUMBER_STYLE = "manual"   # "manual"：手冊 p.49 (七)2／p.52 (八)2；"template"：範本慣例（疑點 B，地政局確認後再切）


def level_number(rule: Rule, level: str | None) -> int | None:
    """
    表1／表5 的「等級數字」欄。
    手冊 p.49 (七)2、p.52 (八)2：2 級 1 優／2 劣，3 級 1／2／3，5 級 1～5 → 等級索引 + 1。
    範本二級細項顯示 1／5、三級 1／3／5（疑點 B）；LEVEL_NUMBER_STYLE = "template" 時照範本。
    """
    if level is None:
        return None
    n = len(rule.levels)
    i = rule.level_index(level)
    if LEVEL_NUMBER_STYLE == "template":
        if n == 3:
            return [1, 3, 5][i]
        if n == 2:
            return [1, 5][i]
    return i + 1
