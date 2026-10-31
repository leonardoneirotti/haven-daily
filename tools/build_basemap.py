"""Build the port basemap (land shapes, land detail, place labels) from OpenStreetMap data.

Run it once, or again when the map area changes. The daily build does not need
it: the result is committed as static/basemap.js and data/basemap/land.geojson.

    .venv\\Scripts\\python.exe -m pip install -r requirements-dev.txt
    .venv\\Scripts\\python.exe tools/build_basemap.py

How it works: OpenStreetMap has no "sea" shape, only coastlines (with land on
the left of each line) and water areas such as rivers and harbour basins. We cut
the map rectangle along the coastlines, keep the pieces on the sea side, add the
water areas, and everything left over is land.

The land detail (roads, railways, breakwaters, storage tanks) gives the chart
its texture. It is stored compactly: coordinates on a grid of 0.0001 degrees
(about 10 m), each point written as the step from the previous one.

Map data © OpenStreetMap contributors, available under the Open Database Licence.
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

from shapely.affinity import scale
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Point, Polygon, box, mapping
from shapely.ops import linemerge, polygonize, unary_union

PROJECT_DIR = Path(__file__).resolve().parent.parent
# The main Overpass server is often busy; the others are public mirrors of the same data.
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
]

# South, west, north, east: from the North Sea anchorages to Rotterdam city, with
# open sea to the west, where the news panel covers the chart on wide screens.
BBOX = (51.74, 3.40, 52.16, 4.62)
# Raw downloads, not committed. Delete one to download it again.
CACHE = PROJECT_DIR / "data" / "basemap" / "osm-cache.json"
DETAIL_CACHE = PROJECT_DIR / "data" / "basemap" / "osm-detail-cache.json"
SIMPLIFY_DEG = 0.0002  # about 15-20 m, under one pixel at the map's normal zoom
DETAIL_SIMPLIFY_DEG = 0.0001  # about 10 m: roads and railways
MIN_LAND_DEG2 = 6e-6  # drop islets smaller than roughly 250 x 150 m
MIN_HOLE_DEG2 = 2.5e-5  # fill ponds and polder ditches smaller than roughly 500 x 350 m
MIN_TANK_RADIUS_M = 4  # smaller tanks are invisible at any zoom the chart allows

# Road classes drawn on the chart, and how they are grouped (major roads are drawn wider).
ROAD_GROUPS = {"motorway": "major", "trunk": "major", "primary": "major", "secondary": "minor", "tertiary": "minor"}

# Place names drawn on the chart. Water names are set in italic, as on nautical charts;
# "angle" turns a label to follow its channel (degrees, clockwise).
LABELS = [
    {"text": "North Sea", "kind": "water", "lat": 51.99, "lon": 3.84},
    {"text": "Nieuwe Waterweg", "kind": "water", "lat": 51.951, "lon": 4.163, "angle": 37},
    {"text": "Nieuwe Maas", "kind": "water", "lat": 51.9, "lon": 4.4},
    {"text": "Oude Maas", "kind": "water", "lat": 51.846, "lon": 4.36, "angle": 30},
    {"text": "Waalhaven", "kind": "water", "lat": 51.879, "lon": 4.452},
    {"text": "Maasvlakte 2", "kind": "land", "lat": 51.976, "lon": 3.975},
    {"text": "Maasvlakte", "kind": "land", "lat": 51.946, "lon": 4.035},
    {"text": "Europoort", "kind": "land", "lat": 51.933, "lon": 4.13},
    {"text": "Botlek", "kind": "land", "lat": 51.868, "lon": 4.29},
    {"text": "Pernis", "kind": "land", "lat": 51.882, "lon": 4.385},
    {"text": "Hoek van Holland", "kind": "land", "lat": 51.984, "lon": 4.135},
    {"text": "Rozenburg", "kind": "land", "lat": 51.906, "lon": 4.245},
    {"text": "Rotterdam", "kind": "city", "lat": 51.925, "lon": 4.48},
]


AREA = "{},{},{},{}".format(*BBOX)

# Coastlines and water areas: everything needed to work out where the land is.
WATER_QUERY = f"""
[out:json][timeout:180];
(
  way["natural"="coastline"]({AREA});
  way["natural"="water"]({AREA});
  relation["natural"="water"]({AREA});
  way["waterway"="riverbank"]({AREA});
  relation["waterway"="riverbank"]({AREA});
);
out geom;
"""

# Land detail. Tunnels are left out: they would draw roads across the water.
DETAIL_QUERY = f"""
[out:json][timeout:180];
(
  way["highway"~"^({"|".join(ROAD_GROUPS)})$"]["tunnel"!="yes"]({AREA});
  way["railway"="rail"]["tunnel"!="yes"]({AREA});
  way["man_made"~"^(breakwater|groyne)$"]({AREA});
  way["man_made"="storage_tank"]({AREA});
);
out geom;
"""


def fetch_osm(cache: Path, query: str) -> dict:
    """Run an Overpass query, or reuse the last download."""
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))
    data = download_osm(query)
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(data), encoding="utf-8")
    return data


def download_osm(query: str) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode()
    headers = {"User-Agent": "haven-daily-basemap/1.0 (personal portfolio project)"}
    for url in OVERPASS_URLS:
        try:
            request = urllib.request.Request(url, data=body, headers=headers)
            with urllib.request.urlopen(request, timeout=240) as response:
                return json.load(response)
        except OSError as error:  # HTTP errors and timeouts: try the next server
            print(f"{url} failed: {error}")
    raise SystemExit("All Overpass servers failed. Try again in a few minutes.")


def coords(geometry: list[dict]) -> list[tuple[float, float]]:
    return [(point["lon"], point["lat"]) for point in geometry if point]


def relation_polygon(relation: dict):
    """Join a multipolygon relation's member lines into one shape (outer minus inner rings)."""
    outers, inners = [], []
    for member in relation.get("members", []):
        if member["type"] != "way" or len(member.get("geometry") or []) < 2:
            continue
        line = LineString(coords(member["geometry"]))
        (inners if member.get("role") == "inner" else outers).append(line)
    if not outers:
        return None
    shape = unary_union(list(polygonize(unary_union(outers))))
    if inners:
        shape = shape.difference(unary_union(list(polygonize(unary_union(inners)))))
    return shape.buffer(0)


def is_sea(face: Polygon, coastlines: list[LineString]) -> bool:
    """True if the face lies on the sea side (right-hand side) of the nearest coastline."""
    p = face.representative_point()
    best = None
    for line in coastlines:
        pts = list(line.coords)
        for a, b in zip(pts, pts[1:]):
            d = LineString([a, b]).distance(p)
            if best is None or d < best[0]:
                best = (d, a, b)
    _, (ax, ay), (bx, by) = best
    cross = (bx - ax) * (p.y - ay) - (by - ay) * (p.x - ax)
    return cross < 0


def clean(shape) -> list[Polygon]:
    polygons = shape.geoms if isinstance(shape, MultiPolygon) else [shape]
    kept = []
    for polygon in polygons:
        if polygon.area < MIN_LAND_DEG2:
            continue
        holes = [ring for ring in polygon.interiors if Polygon(ring).area >= MIN_HOLE_DEG2]
        polygon = Polygon(polygon.exterior, holes).simplify(SIMPLIFY_DEG, preserve_topology=True)
        if not polygon.is_empty:
            kept.append(polygon)
    return kept


def rounded(geometry: dict) -> dict:
    def walk(value):
        if isinstance(value, (list, tuple)):
            if value and isinstance(value[0], float):
                return [round(value[0], 4), round(value[1], 4)]  # about 10 m
            return [walk(item) for item in value]
        return value

    return {"type": geometry["type"], "coordinates": walk(geometry["coordinates"])}


def encode_line(line: LineString) -> list[int]:
    """A line as whole grid steps: the first point counted from the map's
    south-west corner, every next point as the step from the one before."""
    s, w = BBOX[0], BBOX[1]
    steps, px, py = [], 0, 0
    for lon, lat in line.coords:
        x, y = round((lon - w) * 10_000), round((lat - s) * 10_000)
        if steps and (x, y) == (px, py):
            continue
        steps += [x - px, y - py]
        px, py = x, y
    return steps if len(steps) >= 4 else []


def lines_of(shape) -> list[LineString]:
    if shape.is_empty:
        return []
    if isinstance(shape, LineString):
        return [shape]
    return [part for part in getattr(shape, "geoms", []) if isinstance(part, LineString)]


def build_detail(area: Polygon) -> dict:
    """Roads, railways and breakwaters as lines; storage tanks as circles (centre and radius in metres)."""
    data = fetch_osm(DETAIL_CACHE, DETAIL_QUERY)
    lat0 = math.radians((BBOX[0] + BBOX[2]) / 2)
    metres_per_degree = (111_320 * math.cos(lat0), 110_540)  # longitude, latitude

    groups: dict[str, list[LineString]] = {"major": [], "minor": [], "rail": [], "jetty": []}
    tanks = []
    for element in data["elements"]:
        tags = element.get("tags", {})
        points = coords(element.get("geometry", []))
        if element["type"] != "way" or len(points) < 2:
            continue
        if tags.get("man_made") == "storage_tank":
            if len(points) < 4 or points[0] != points[-1]:
                continue
            tank = Polygon(points)
            if not tank.is_valid or not area.contains(tank.centroid):
                continue
            radius = math.sqrt(scale(tank, *metres_per_degree, origin=(0, 0)).area / math.pi)
            if radius >= MIN_TANK_RADIUS_M:
                tanks.append((tank.centroid, radius))
        elif tags.get("highway") in ROAD_GROUPS:
            groups[ROAD_GROUPS[tags["highway"]]].append(LineString(points))
        elif tags.get("railway") == "rail":
            groups["rail"].append(LineString(points))
        else:
            groups["jetty"].append(LineString(points))

    detail: dict = {"grid": 10_000}
    for name, lines in groups.items():
        # Join ways that continue each other, so the page draws fewer, longer lines.
        merged = linemerge(MultiLineString(lines)).intersection(area).simplify(DETAIL_SIMPLIFY_DEG)
        detail[name] = [steps for line in lines_of(merged) if (steps := encode_line(line))]
    s, w = BBOX[0], BBOX[1]
    detail["tanks"] = [
        value
        for centre, radius in tanks
        for value in (round((centre.x - w) * 10_000), round((centre.y - s) * 10_000), round(radius))
    ]
    counts = ", ".join(f"{len(detail[name])} {name}" for name in groups)
    print(f"Detail: {counts} lines, {len(tanks)} tanks")
    return detail


def build() -> None:
    s, w, n, e = BBOX
    area = box(w, s, e, n)
    data = fetch_osm(CACHE, WATER_QUERY)

    coastlines, water = [], []
    for element in data["elements"]:
        tags = element.get("tags", {})
        if element["type"] == "way":
            points = coords(element.get("geometry", []))
            if len(points) < 2:
                continue
            if tags.get("natural") == "coastline":
                coastlines.append(LineString(points))
            elif len(points) >= 4 and points[0] == points[-1]:
                water.append(Polygon(points).buffer(0))
        elif element["type"] == "relation":
            shape = relation_polygon(element)
            if shape is not None and not shape.is_empty:
                water.append(shape)

    pieces = [line.intersection(area) for line in coastlines]
    noded = unary_union([area.exterior] + [piece for piece in pieces if not piece.is_empty])
    sea = [face for face in polygonize(noded) if coastlines and is_sea(face, coastlines)]

    all_water = unary_union(sea + [shape.intersection(area) for shape in water])
    land = clean(area.difference(all_water))
    land_geometry = rounded(mapping(MultiPolygon(land)))

    out_data = PROJECT_DIR / "data" / "basemap"
    out_data.mkdir(parents=True, exist_ok=True)
    (out_data / "land.geojson").write_text(json.dumps(land_geometry), encoding="utf-8")

    basemap = {"bbox": [s, w, n, e], "land": land_geometry, "detail": build_detail(area), "labels": LABELS}
    script = (
        "// Generated by tools/build_basemap.py. Do not edit by hand.\n"
        "// Map data (c) OpenStreetMap contributors, ODbL.\n"
        f"window.HAVEN_BASEMAP = {json.dumps(basemap, separators=(',', ':'))};\n"
    )
    (PROJECT_DIR / "static" / "basemap.js").write_text(script, encoding="utf-8")
    print(
        f"{len(coastlines)} coastline ways, {len(water)} water areas, "
        f"{len(sea)} sea faces -> {len(land)} land polygons, basemap.js {len(script) // 1024} KB"
    )


if __name__ == "__main__":
    build()
