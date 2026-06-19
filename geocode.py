"""拠点名→緯度経度変換（Nominatim / OpenStreetMap）。"""
import time
import pandas as pd

try:
    from geopy.geocoders import Nominatim
    from geopy.exc import GeocoderTimedOut, GeocoderServiceError
    HAS_GEOPY = True
except ImportError:
    HAS_GEOPY = False

_geolocator = Nominatim(user_agent="logistics_dashboard_v2") if HAS_GEOPY else None

# 境町拠点の既知座標（即時利用可能）
KNOWN_COORDS = {
    "GS境": (36.2215, 139.8340),
    "GS境拠点": (36.2215, 139.8340),
    "境町": (36.2215, 139.8340),
    "美里工場": (36.3042, 137.1371),
    "熊谷センター": (36.1473, 139.3886),
    "大宮DC": (35.9069, 139.6236),
    "越谷DC": (35.8908, 139.7894),
    "川越DC": (35.9252, 139.4853),
    "さいたまDC": (35.8617, 139.6455),
    "志木DC": (35.8328, 139.5780),
    "春日部DC": (35.9756, 139.7526),
    "アスカット": (36.1800, 139.4500),
    "ヤオコー": (36.0700, 139.4200),
    "カネミ食品": (36.0500, 139.5000),
    "ヨシケイ栃木": (36.5600, 139.8800),
    "DIC信濃川上": (35.9500, 138.4500),
    "東京シティ": (35.6800, 139.7700),
    "境町給食": (36.2215, 139.8340),
}


def geocode_address(address: str, retries: int = 3) -> tuple[float | None, float | None]:
    if address in KNOWN_COORDS:
        return KNOWN_COORDS[address]
    if not HAS_GEOPY or _geolocator is None:
        return None, None
    for attempt in range(retries):
        try:
            loc = _geolocator.geocode(address, timeout=10)
            if loc:
                return loc.latitude, loc.longitude
            return None, None
        except GeocoderTimedOut:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
        except GeocoderServiceError:
            return None, None
    return None, None


def build_facility_lookup(master_df: pd.DataFrame | None = None) -> dict[str, tuple[float, float]]:
    """拠点マスタ DataFrame から {拠点名: (緯度, 経度)} の辞書を返す。既知座標を常に含む。"""
    lookup = dict(KNOWN_COORDS)
    if master_df is not None and not master_df.empty:
        for _, row in master_df.iterrows():
            name = str(row.get("拠点名", "")).strip()
            lat = row.get("緯度")
            lng = row.get("経度")
            if name and lat and lng:
                try:
                    lookup[name] = (float(lat), float(lng))
                except (ValueError, TypeError):
                    pass
    return lookup
