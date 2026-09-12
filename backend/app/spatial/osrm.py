"""OSRM foot profile 路徑距離（deploy/osrm.md）。任何失敗都丟 OSRMError，由 distance.py 決定退回直線估算。"""
from __future__ import annotations

import os

import httpx


class OSRMError(RuntimeError):
    pass


class OSRMClient:
    def __init__(self, base_url: str | None = None, profile: str = "foot", timeout: float = 3.0,
                 client: httpx.Client | None = None):
        self.base_url = (base_url or os.environ.get("OSRM_URL") or "").rstrip("/")
        self.profile = profile
        self.timeout = timeout
        self._client = client or httpx.Client(timeout=timeout)
        self._available: bool | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.base_url)

    def _get(self, path: str, params: dict | None = None) -> dict:
        if not self.enabled:
            raise OSRMError("OSRM_URL 未設定")
        try:
            r = self._client.get(f"{self.base_url}{path}", params=params)
        except httpx.HTTPError as e:
            self._available = False
            raise OSRMError(f"OSRM 連線失敗：{e}") from e
        if r.status_code != 200:
            raise OSRMError(f"OSRM HTTP {r.status_code}：{r.text[:200]}")
        data = r.json()
        if data.get("code") != "Ok":
            raise OSRMError(f"OSRM {data.get('code')}：{data.get('message', '')}")
        self._available = True
        return data

    def snap(self, lon: float, lat: float) -> tuple[float, float]:
        d = self._get(f"/nearest/v1/{self.profile}/{lon},{lat}", {"number": 1})
        loc = d["waypoints"][0]["location"]
        return float(loc[0]), float(loc[1])

    def route_distance_m(self, a: tuple[float, float], b: tuple[float, float]) -> float:
        """步行路徑距離（公尺）。起終點先 snap 到路網。"""
        d = self._get(f"/route/v1/{self.profile}/{a[0]},{a[1]};{b[0]},{b[1]}", {"overview": "false", "alternatives": "false"})
        return float(d["routes"][0]["distance"])

    def status(self) -> dict:
        return {"enabled": self.enabled, "base_url": self.base_url, "profile": self.profile, "last_ok": self._available}
