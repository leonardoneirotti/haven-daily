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
its texture.

Everything the browser gets is stored compactly (#104): coordinates on a grid of
0.0001 degrees (about 10 m), each point written as the step from the previous one,
and each step in 5-bit groups as letters (the "encoded polyline" scheme of web maps).
Shapes are sorted by position, and a shape's first point is the step from the first
point of the shape before it, so the steps stay small. The chart's shapes are also
simpler than the land in data/basemap/land.geojson, which keeps the finer outline.

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
SIMPLIFY_DEG = 0.0002  # about 15-20 m: the land in data/basemap/land.geojson
# The chart's shapes, simpler (#104): the most a simplified line may stray from the original.
# The chart shows an item at zoom 13.6 at most, about 8 m per pixel.
CHART_LAND_SIMPLIFY_DEG = 0.0004  # about 25-45 m
CHART_DETAIL_SIMPLIFY_DEG = {"major": 0.0002, "minor": 0.0004, "rail": 0.0002, "jetty": 0.0002}
MIN_MINOR_ROAD_M = 150  # shorter pieces of minor road are left out (texture, not navigation)
MAX_AREA_CHANGE = 0.10  # a piece of land that simplifying changes more than this keeps its finer outline
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
        # Each point as a (lon, lat) pair instead of a dictionary: about a third of the memory
        # for the ~2 million points (the owner's laptop has little to spare; #104).
        return json.loads(cache.read_text(encoding="utf-8"), object_hook=point_pair)
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


def point_pair(value: dict):
    return (value["lon"], value["lat"]) if value.keys() == {"lat", "lon"} else value


def coords(geometry: list) -> list[tuple[float, float]]:
    return [point if isinstance(point, tuple) else (point["lon"], point["lat"]) for point in geometry if point]


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


GRID = 10_000  # grid points per degree


def grid_points(line) -> list[tuple[int, int]]:
    """A line's points on the grid, counted from the map's south-west corner, repeats left out."""
    s, w = BBOX[0], BBOX[1]
    points = []
    for lon, lat in line.coords:
        point = (round((lon - w) * GRID), round((lat - s) * GRID))
        if not points or point != points[-1]:
            points.append(point)
    return points


def polyline_text(numbers: list[int]) -> str:
    """Whole numbers as letters, 5 bits per letter (the "encoded polyline" scheme): the sign
    goes into the lowest bit, then 5-bit groups from the lowest, each but the last + 32,
    all + 63 so they are printable. Small steps take one letter."""
    letters = []
    for number in numbers:
        value = ~(number << 1) if number < 0 else number << 1
        while value >= 0x20:
            letters.append(chr((0x20 | (value & 0x1F)) + 63))
            value >>= 5
        letters.append(chr(value + 63))
    return "".join(letters)


def polyline_numbers(text: str) -> list[int]:
    """The reverse of polyline_text (map.js has the same in JavaScript)."""
    numbers, value, shift = [], 0, 0
    for letter in text:
        c = ord(letter) - 63
        value |= (c & 0x1F) << shift
        if c & 0x20:
            shift += 5
            continue
        numbers.append(~(value >> 1) if value & 1 else value >> 1)
        value, shift = 0, 0
    return numbers


def by_position(point: tuple[int, int]) -> tuple[int, int]:
    """Sort order: bands of 64 grid rows (about 700 m) from the south, west to east in each."""
    return (point[1] // 64, point[0])


def encode_shapes(shapes: list[list[tuple[int, int]]]) -> list[str]:
    """Each shape as text: its first point as the step from the first point of the shape
    before it (sorted by position, so that step is short), then the steps between its points."""
    texts, start = [], (0, 0)
    for points in sorted((p for p in shapes if len(p) >= 2), key=lambda p: by_position(p[0])):
        steps, (px, py) = [], start
        for x, y in points:
            steps += [x - px, y - py]
            px, py = x, y
        texts.append(polyline_text(steps))
        start = points[0]
    return texts


def decode_shapes(texts: list[str]) -> list[list[tuple[int, int]]]:
    """The reverse of encode_shapes: grid points again."""
    shapes, start = [], (0, 0)
    for text in texts:
        numbers = polyline_numbers(text)
        x, y = start
        points = []
        for i in range(0, len(numbers), 2):
            x, y = x + numbers[i], y + numbers[i + 1]
            points.append((x, y))
        shapes.append(points)
        start = points[0]
    return shapes


def encode_tanks(tanks: list[tuple[int, int, int]]) -> str:
    """Tanks as one text: per tank the step from the tank before (sorted by position) and its radius in metres."""
    numbers, (px, py) = [], (0, 0)
    for x, y, radius in sorted(tanks, key=lambda t: by_position((t[0], t[1]))):
        numbers += [x - px, y - py, radius]
        px, py = x, y
    return polyline_text(numbers)


def chart_shape(polygon: Polygon) -> Polygon:
    """A piece of land, simpler for the chart. A narrow piece (a dam, a long pier) would
    collapse at the chart's tolerance, so a piece whose area changes by more than
    MAX_AREA_CHANGE keeps the finer outline it has in land.geojson."""
    simple = polygon.simplify(CHART_LAND_SIMPLIFY_DEG, preserve_topology=True)
    if polygon.symmetric_difference(simple).area > MAX_AREA_CHANGE * polygon.area:
        return polygon
    return simple


def length_m(line: LineString) -> float:
    lat0 = math.radians((BBOX[0] + BBOX[2]) / 2)
    return scale(line, 111_320 * math.cos(lat0), 110_540, origin=(0, 0)).length


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

    detail: dict = {}
    for name, lines in groups.items():
        # Join ways that continue each other, so the page draws fewer, longer lines.
        merged = linemerge(MultiLineString(lines)).intersection(area)
        kept = [line.simplify(CHART_DETAIL_SIMPLIFY_DEG[name]) for line in lines_of(merged)
                if name != "minor" or length_m(line) >= MIN_MINOR_ROAD_M]
        detail[name] = encode_shapes([grid_points(line) for line in kept])
    s, w = BBOX[0], BBOX[1]
    detail["tanks"] = encode_tanks([
        (round((centre.x - w) * GRID), round((centre.y - s) * GRID), round(radius)) for centre, radius in tanks
    ])
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

    # The chart's land: simpler, every ring (outer edge or hole) as one shape, filled "evenodd".
    chart_land = [grid_points(ring) for polygon in land for simple in [chart_shape(polygon)]
                  if not simple.is_empty for ring in [simple.exterior, *simple.interiors]]
    basemap = {"bbox": [s, w, n, e], "grid": GRID, "land": encode_shapes(chart_land),
               "detail": build_detail(area), "labels": LABELS}
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
