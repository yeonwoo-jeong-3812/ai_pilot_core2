"""교전 공역 지면 지도 굽기 — Web Mercator 타일을 받아 한 장으로 합친다.

교전 좌표는 engine/state.py:ned_to_lonlat 이 lon0=127.0 / lat0=37.0 으로 찍으므로
기본 중심은 그 지점(경기 남부 내륙)이다. 결과물은 뷰어의 지면 평면에 그대로 입혀진다.

    python tools/acmi_viewer/make_map.py                      # 기본 (Esri 위성, z12, 64km)
    python tools/acmi_viewer/make_map.py --source osm --zoom 12
    python tools/acmi_viewer/make_map.py --lat 37.5 --lon 127.0 --span-km 80 --name seoul

산출물 (static/maps/, git 제외 — 타일 이미지는 재배포하지 않는다):
    <name>.jpg          합성 지도
    index.json          평면 배치용 메타 (중심 위경도·m/px·크기·출처)

★ 평면 근사에 대하여
  엔진 물리는 평지(ned_to_lonlat 은 평면근사, 하드덱은 해수면 1,000ft 고정)다.
  그래서 지도도 **고도 0 의 평면**에 입힌다 — 실지형 고저는 일부러 쓰지 않는다.
  Web Mercator 는 위도에 따라 축척이 변하므로 중심 위도의 m/px 하나로 평면 전체를
  근사한다. 64km 범위·위도 37° 에서 가장자리 축척 오차는 약 0.4%(≈240m)로,
  ENU 트랙과의 정합에 영향이 없다.
"""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path

TILE = 256
EQUATOR_M = 2 * math.pi * 6378137.0  # Web Mercator 적도 둘레

SOURCES = {
    # Esri World Imagery — 위성. 무료 이용 가능(출처 표기 조건).
    "esri": {
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
        "attribution": ("Esri, Maxar, Earthstar Geographics, "
                        "and the GIS User Community"),
        "max_zoom": 17,
    },
    # OSM 표준 타일 — 지도. 타일 사용 정책상 대량 수집 금지이므로 소량만.
    "osm": {
        "url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "attribution": "© OpenStreetMap contributors (ODbL)",
        "max_zoom": 18,
    },
}

STATIC = Path(__file__).resolve().parent / "static"
MAPS_DIR = STATIC / "maps"
UA = "ai-combat-core2-acmi-viewer/1.0 (local research tool)"


def deg2tile(lat: float, lon: float, z: int) -> tuple[float, float]:
    """위경도 → 타일 좌표(소수). Web Mercator 정의 그대로."""
    n = 2.0 ** z
    x = (lon + 180.0) / 360.0 * n
    phi = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(phi)) / math.pi) / 2.0 * n
    return x, y


def tile2deg(x: float, y: float, z: int) -> tuple[float, float]:
    """타일 좌표(소수) → (lat, lon). deg2tile 의 역."""
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lat, lon


def meters_per_pixel(lat: float, z: int) -> float:
    """해당 위도·줌의 지상 해상도 [m/px]."""
    return EQUATOR_M * math.cos(math.radians(lat)) / (TILE * 2.0 ** z)


def fetch_tile(url: str, retries: int = 3) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.read()
        except (urllib.error.URLError, TimeoutError) as exc:  # noqa: PERF203
            last = exc
    raise RuntimeError(f"타일 실패 {url}: {last}")


def build(source: str, lat: float, lon: float, zoom: int, span_km: float,
          name: str) -> dict:
    try:
        from PIL import Image
    except ImportError:  # pragma: no cover - 설치 안내
        sys.exit("Pillow 가 필요합니다 (matplotlib 의존성으로 보통 이미 설치됨): "
                 "pip install pillow")

    spec = SOURCES[source]
    if zoom > spec["max_zoom"]:
        sys.exit(f"{source} 최대 줌은 {spec['max_zoom']} 입니다.")

    mpp = meters_per_pixel(lat, zoom)
    half_px = (span_km * 1000.0 / 2.0) / mpp
    cx, cy = deg2tile(lat, lon, zoom)

    # 요청 범위를 덮는 정수 타일 격자 (실제 산출물은 요청보다 조금 넓어진다)
    x0 = math.floor(cx - half_px / TILE)
    x1 = math.ceil(cx + half_px / TILE)
    y0 = math.floor(cy - half_px / TILE)
    y1 = math.ceil(cy + half_px / TILE)
    nx, ny = x1 - x0, y1 - y0
    total = nx * ny
    if total > 400:
        sys.exit(f"타일 {total}장은 과합니다 — --zoom 을 낮추거나 --span-km 를 줄이세요.")

    print(f"{source} z{zoom}: {nx}×{ny} = {total} 타일  ({mpp:.2f} m/px)")
    canvas = Image.new("RGB", (nx * TILE, ny * TILE))
    for iy in range(ny):
        for ix in range(nx):
            url = spec["url"].format(z=zoom, x=x0 + ix, y=y0 + iy)
            tile = Image.open(io.BytesIO(fetch_tile(url))).convert("RGB")
            canvas.paste(tile, (ix * TILE, iy * TILE))
        print(f"  행 {iy + 1}/{ny}", end="\r", flush=True)
    print()

    # 합성본의 실제 중심 — 타일 경계로 맞춘 격자의 한가운데
    mid_lat, mid_lon = tile2deg((x0 + x1) / 2.0, (y0 + y1) / 2.0, zoom)
    # 축척은 이미지 중심 위도 기준 하나로 통일(위 docstring 의 평면 근사)
    mpp_mid = meters_per_pixel(mid_lat, zoom)

    MAPS_DIR.mkdir(parents=True, exist_ok=True)
    img_name = f"{name}.jpg"
    canvas.save(MAPS_DIR / img_name, "JPEG", quality=88, optimize=True)

    meta = {
        "image": img_name,
        "center_lat": round(mid_lat, 7),
        "center_lon": round(mid_lon, 7),
        "width_px": canvas.width,
        "height_px": canvas.height,
        "meters_per_pixel": round(mpp_mid, 4),
        "width_m": round(canvas.width * mpp_mid, 1),
        "height_m": round(canvas.height * mpp_mid, 1),
        "source": source,
        "zoom": zoom,
        "attribution": spec["attribution"],
    }
    (MAPS_DIR / "index.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    size_mb = (MAPS_DIR / img_name).stat().st_size / 1e6
    print(f"저장: static/maps/{img_name}  "
          f"{canvas.width}×{canvas.height}px  {size_mb:.1f}MB")
    print(f"      {meta['width_m'] / 1000:.1f}×{meta['height_m'] / 1000:.1f} km  "
          f"중심 {mid_lat:.4f}N {mid_lon:.4f}E")
    print(f"출처: {spec['attribution']}")
    return meta


def main() -> None:
    p = argparse.ArgumentParser(description="ACMI 뷰어 지면 지도 생성")
    p.add_argument("--source", choices=sorted(SOURCES), default="esri")
    p.add_argument("--lat", type=float, default=37.0, help="중심 위도 (기본: 교전 원점)")
    p.add_argument("--lon", type=float, default=127.0, help="중심 경도 (기본: 교전 원점)")
    p.add_argument("--zoom", type=int, default=12, help="Web Mercator 줌 (기본 12 ≈ 30m/px)")
    p.add_argument("--span-km", type=float, default=64.0, help="한 변 길이 [km]")
    p.add_argument("--name", default="arena", help="산출 파일 이름 (기본 arena)")
    args = p.parse_args()
    build(args.source, args.lat, args.lon, args.zoom, args.span_km, args.name)


if __name__ == "__main__":
    main()
