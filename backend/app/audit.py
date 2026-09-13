"""
操作紀錄（沒有登入的過渡做法）：每個案件一個 JSONL，記「誰（姓名＋角色）在何時做了什麼、改了哪些欄位」。
身分由前端以 header 送來（X-Actor-Name／X-Actor-Role，值經 URL 編碼），角色三種：承辦／審查人／估價師。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import unquote

ROLES = {"officer": "承辦", "reviewer": "審查人", "appraiser": "估價師"}
ACTIONS = {"income": "收益法", 
    "create": "建立案件", "save": "儲存案件資料", "patch": "更新案件", "status": "變更狀態", "decisions": "儲存承辦裁決",
    "duplicate": "複製案件", "delete": "刪除案件", "generate": "重新產生書表", "reset": "重置案件", "clear": "清空輸入重填", "from_lot": "依地號產生", "comparables": "採用實價登錄實例", "polish": "語言模型潤飾文字", "import": "匯入檔案", "input": "加入輸入檔", "input_remove": "移除輸入檔", "archive": "封存案件", "unarchive": "復原案件", "report": "產生審查意見書", "export": "匯出 Excel 書表", "figure": "匯出圖說",
}
STATUS_ZH = {"draft": "草稿", "reviewing": "審查中", "done": "已完成"}
MAX_CHANGES = 40


def _audit_dir():
    from app import cases as C
    d = C.CASES_DIR.parent / "audit"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now() -> str:
    return datetime.now(tz=timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def actor_from_headers(headers: Any) -> dict[str, str]:
    name = unquote(headers.get("x-actor-name", "") or "")
    role = (headers.get("x-actor-role", "") or "").strip()
    return {"name": name.strip(), "role": role if role in ROLES else ""}


def actor_label(actor: dict[str, str] | None) -> str:
    if not actor or not (actor.get("name") or actor.get("role")):
        return "未登記身分"
    n, r = actor.get("name") or "", ROLES.get(actor.get("role") or "", "")
    return f"{n}（{r}）" if n and r else (n or r)


def flatten(obj: Any, prefix: str = "") -> dict[str, Any]:
    """巢狀 dict/list → {路徑: 值}，路徑用 a.b[0].c 形式，值只到葉節點。"""
    out: dict[str, Any] = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.update(flatten(v, f"{prefix}.{k}" if prefix else str(k)))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.update(flatten(v, f"{prefix}[{i}]"))
    else:
        out[prefix] = obj
    return out


def diff_paths(old: Any, new: Any, *, ignore_prefixes: tuple[str, ...] = ("provenance",)) -> list[dict[str, Any]]:
    """兩份資料的欄位差異：[{path, old, new}]，忽略 provenance 之類的佐證欄位；最多 MAX_CHANGES 筆。"""
    a, b = flatten(old or {}), flatten(new or {})
    changes = []
    for p in sorted(set(a) | set(b)):
        if any(seg.startswith(ignore_prefixes) for seg in p.replace("[", ".").split(".")):
            continue
        if a.get(p, "__missing__") != b.get(p, "__missing__"):
            changes.append({"path": p, "old": a.get(p), "new": b.get(p)})
    return changes[:MAX_CHANGES] + ([{"path": f"…另 {len(changes) - MAX_CHANGES} 處", "old": None, "new": None}] if len(changes) > MAX_CHANGES else [])


def log(cid: str, actor: dict[str, str] | None, action: str, detail: str = "", changes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    entry = {"at": _now(), "actor": actor or {}, "actor_label": actor_label(actor), "action": action,
             "action_label": ACTIONS.get(action, action), "detail": detail, "changes": changes or []}
    with (_audit_dir() / f"{cid}.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def read(cid: str, limit: int = 200) -> list[dict[str, Any]]:
    p = _audit_dir() / f"{cid}.jsonl"
    if not p.exists():
        return []
    rows = [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
    return list(reversed(rows))[:limit]


def copy_log(src: str, dst: str, actor: dict[str, str] | None) -> None:
    """複製案件時把原紀錄帶過去（標示來源），再記一筆複製。"""
    old = read(src, limit=10_000)
    if old:
        with (_audit_dir() / f"{dst}.jsonl").open("a", encoding="utf-8") as fh:
            for e in reversed(old):
                fh.write(json.dumps({**e, "inherited_from": src}, ensure_ascii=False) + "\n")
    log(dst, actor, "duplicate", f"自案件 {src} 複製")
