"""
空間模組：把「宗地／區段在哪裡」變成勘查表與清冊要的「到各設施的距離、區段內有無」。

  geo.py        座標（WGS84 ↔ TWD97 EPSG:3826）、直線距離、質心、區段邊界最近點、臨路邊界點
  poi.py        POI 庫（記憶體 / SQLite / GeoJSON），type 用 rules/facility_measurement.json 的 key
  osrm.py       OSRM foot 路徑距離；失敗退回直線 ×1.3 並標 straight_estimated
  distance.py   單筆量測 → Facility（每筆都帶 measure / origin / source / 計算佐證）
  reference.py  案件層級參照設施（手冊 p.24 8(2)、p.51 (六)2(2)）與 fill_parcel / fill_section

法源：手冊 p.24 8(1)-(3)（量測標準：需通達者路線距離、嫌惡設施直線距離；同案一致；多設施取影響最大者）、
p.51 (六)2(2)（比較標的接近條件除非另有同等級設施否則填與比準地相同標的）。
量測起點是推定（區域因素：區段邊界最近點；個別因素：宗地質心），輸出一律標 origin 並可切換。
"""
from .distance import facility_from_poi, measure_distance
from .geo import as_shape, boundary_nearest_point, centroid, frontage_point, straight_distance_m
from .osrm import OSRMClient, OSRMError
from .poi import POI, POIStore
from .reference import fill_parcel, fill_section, mode_for_type, select_reference_facilities

__all__ = [
           "POI",
           "OSRMClient",
           "OSRMError",
           "POIStore",
           "as_shape",
           "boundary_nearest_point",
           "centroid",
           "facility_from_poi",
           "fill_parcel",
           "fill_section",
           "frontage_point",
           "measure_distance",
           "mode_for_type",
           "select_reference_facilities",
           "straight_distance_m",
]
