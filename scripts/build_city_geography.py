"""Build the city geography table, and repair the expanded city coordinates.

One run does three jobs, in this order:

1. **Repair** — thirteen expanded cities carry the coordinate of a same-named
   village *inside the same province*: ``scripts/expand_cities.py`` compares
   ``admin1`` only, so it passes while the prefecture (``admin2``) is a different
   city 115-683 km away. Each repair is a geocoding lookup by id, verified against
   the city name and the province before anything is written. Only the matched
   columns of those lines change, so the CSV diff stays readable.
2. **Extend** — Hong Kong, Macao and two Taiwanese cities join the roster (185
   cities, 34 province-level units). These are queried *without*
   ``countryCode=CN``: their ``country_code`` is HK/MO/TW, ``admin1`` is either
   absent or an entity name, and the Chinese name of a Taiwanese city resolves to
   nothing at all (the pinyin form is what works).
3. **Geography** — ``backend/city_geography.csv``: real elevation (city centre plus
   four 0.25-degree neighbours, requested 100 points at a time), a relief proxy
   from that spread, and population from the geocoding record. Road density,
   industrial share and emission intensity are **synthetic** because the real
   sources are not reachable: every Overpass mirror answered 406/500/403/timeout
   and the Geofabrik China extract is 1.61 GB. The last two columns of the CSV
   state which numbers are real and which are synthetic, so the boundary is
   readable from the data itself rather than from memory.

Usage: uv run python -m scripts.build_city_geography   # safe to re-run; cached in data/
"""

from __future__ import annotations

import csv
import json
import math
import random
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from backend.city_catalog import BASE_CITY_CATALOG
from scripts.expand_cities import normalize_province, strip_suffix

GEOCODING_SEARCH = "https://geocoding-api.open-meteo.com/v1/search"
GEOCODING_BY_ID = "https://geocoding-api.open-meteo.com/v1/get"
ELEVATION = "https://api.open-meteo.com/v1/elevation"

BACKEND = Path(__file__).resolve().parent.parent / "backend"
CATALOG_PATH = BACKEND / "city_geocoding.csv"
GEOGRAPHY_PATH = BACKEND / "city_geography.csv"
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "_geocoding_cache.json"

# Real columns come from these two endpoints; everything else in the geography
# table is synthetic and says so per row.
REAL_SOURCE = "open-meteo:geocoding(geonames)+elevation"
SYNTHETIC_SEED = 20261016
SYNTHETIC_NOTE = f"roads/industry/emission synthetic (seed {SYNTHETIC_SEED})"
RELIEF_OFFSET = 0.25  # ~25 km; the spread over these five points is the relief proxy

# city -> verified geocoding id (docs/规划.md 2.2). The id is the whole point: it
# selects the prefecture record instead of whichever village shares the name.
REPAIRS = {
    "德阳": 1812961,
    "九江": 1805179,
    "普洱": 1794209,
    "阳江": 1806408,
    "东营": 1812101,
    "舟山": 1886762,
    "周口": 1784130,
    "邵阳": 1816920,
    "榆林": 1785777,
    "枣庄": 1785453,
    "安阳": 1785294,
    "岳阳": 1927639,
    "芜湖": 1791236,
}
# Two records carry a name the CSV does not use: 普洱's prefecture was renamed (the
# GeoNames record for the urban district is still 思茅) and the Zhoushan record is
# only reachable — and only named — in pinyin.
RECORD_ALIAS = {"普洱": ("思茅",), "舟山": ("Zhoushan",)}

# province-level units that are not queried with countryCode=CN: the filter drops
# them entirely, and admin1 cannot be used as the acceptance test.
NEW_CITIES = (
    ("香港", "香港", "华南", ("香港", "Hong Kong")),
    ("澳门", "澳门", "华南", ("澳门", "Macau")),
    ("台北", "台湾", "华东", ("Taipei", "台北市")),
    ("高雄", "台湾", "华东", ("Kaohsiung", "高雄市")),
)
SPECIAL_COUNTRIES = {"HK", "MO", "TW"}

# The base 60 have no stored geocoding id, so their population comes from a name
# lookup; a few only resolve with the pinyin form.
EXTRA_TERMS = {"宝鸡": ("Baoji",), "太原": ("Taiyuan",), "咸阳": ("Xianyang",)}


@dataclass(frozen=True)
class City:
    location_id: int
    city: str
    province: str
    region: str
    latitude: float
    longitude: float
    geocoding_id: int | None


def _fetch(url: str, cache: dict[str, object]) -> dict:
    if url in cache:
        return cache[url]  # type: ignore[return-value]
    last: Exception | None = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(url, timeout=25) as response:
                payload = json.loads(response.read().decode("utf-8"))
            cache[url] = payload
            return payload
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(2.0 + 3.0 * attempt)
    raise RuntimeError(f"geocoding request failed: {url}") from last


def _search(term: str, cache: dict, country: str | None = None) -> list[dict]:
    params = {"name": term, "count": 10, "language": "zh"}
    if country:
        params["countryCode"] = country
    payload = _fetch(f"{GEOCODING_SEARCH}?{urllib.parse.urlencode(params)}", cache)
    time.sleep(0.4)
    return payload.get("results") or []


def _by_id(geocoding_id: int, cache: dict) -> dict:
    payload = _fetch(f"{GEOCODING_BY_ID}?id={geocoding_id}&language=zh", cache)
    time.sleep(0.4)
    return payload


def _distance_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(a[0]), math.radians(b[0])
    dphi = phi2 - phi1
    dlambda = math.radians(b[1] - a[1])
    inner = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(inner))


def _record_names(city: str, record: dict) -> bool:
    name = strip_suffix(record.get("name", ""))
    return name == city or name in RECORD_ALIAS.get(city, ())


def read_catalog() -> list[City]:
    """The catalog as the database sees it: the base 60 plus the CSV block."""
    with CATALOG_PATH.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    base = [
        City(row.location_id, row.name, row.province, row.region,
             row.latitude, row.longitude, None)
        for row in BASE_CITY_CATALOG
    ]
    extra = [
        City(
            int(row["location_id"]),
            row["city"],
            row["province"],
            row["region"],
            float(row["latitude"]),
            float(row["longitude"]),
            int(row["open_meteo_geocoding_id"]),
        )
        for row in rows
    ]
    return base + extra


def repair_coordinates(cache: dict) -> list[str]:
    """Rewrite the matched lines of backend/city_geocoding.csv in place."""
    # Line endings are mixed in this file (hand-grown CSV); each line keeps its own
    # so the diff shows only the values that changed.
    with CATALOG_PATH.open(encoding="utf-8", newline="") as handle:
        lines = handle.read().splitlines(keepends=True)

    report: list[str] = []
    for index, line in enumerate(lines):
        cells = line.rstrip("\r\n").split(",")
        if len(cells) != 7 or cells[1] not in REPAIRS:
            continue
        city = cells[1]
        record = _by_id(REPAIRS[city], cache)
        if not _record_names(city, record):
            raise RuntimeError(f"{city}: id {REPAIRS[city]} resolved to {record.get('name')!r}")
        admin1 = normalize_province(record.get("admin1", ""))
        if admin1 != normalize_province(cells[2]):
            raise RuntimeError(f"{city}: id {REPAIRS[city]} sits in {admin1!r}, not {cells[2]}")
        old = (float(cells[4]), float(cells[5]))
        new = (round(float(record["latitude"]), 5), round(float(record["longitude"]), 5))
        moved = _distance_km(old, new)
        if moved < 1.0:
            report.append(f"  = {city:4} already correct ({moved:.1f} km)")
            continue
        ending = line[len(line.rstrip("\r\n")):]
        cells[4], cells[5], cells[6] = f"{new[0]:.5f}", f"{new[1]:.5f}", str(record["id"])
        lines[index] = ",".join(cells) + ending
        report.append(
            f"  > {city:4} {old[0]:.4f},{old[1]:.4f} -> {new[0]:.4f},{new[1]:.4f}"
            f"  ({moved:.0f} km, admin2={record.get('admin2')}, pop={record.get('population')})"
        )
    CATALOG_PATH.write_text("".join(lines), encoding="utf-8", newline="")
    return report


def add_special_cities(cache: dict) -> list[str]:
    """Append the HK/MO/TW rows, accepted by country_code instead of admin1."""
    catalog = read_catalog()
    present = {row.city for row in catalog}
    pending = [entry for entry in NEW_CITIES if entry[0] not in present]
    if not pending:
        return ["  = Hong Kong, Macao and Taiwan already in the catalog"]
    next_id = max(row.location_id for row in catalog) + 1
    report: list[str] = []
    with CATALOG_PATH.open(encoding="utf-8", newline="") as handle:
        existing = handle.read()
    ending = "\r\n" if existing.endswith("\r\n") else "\n"
    if not existing.endswith(("\n", "\r")):
        existing += ending
    additions: list[str] = []
    for city, province, region, terms in pending:
        record = None
        for term in terms:
            for item in _search(term, cache):
                if item.get("country_code") not in SPECIAL_COUNTRIES:
                    continue
                if strip_suffix(item.get("name", "")) != city and item.get("name") != city:
                    continue
                record = item
                break
            if record:
                break
        if record is None:
            raise RuntimeError(f"{city}: no record in {sorted(SPECIAL_COUNTRIES)}")
        additions.append(
            f"{next_id},{city},{province},{region},"
            f"{round(float(record['latitude']), 5):.5f},{round(float(record['longitude']), 5):.5f},"
            f"{record['id']}{ending}"
        )
        report.append(
            f"  + {city:4} id={next_id} {record['latitude']:.3f},{record['longitude']:.3f}"
            f"  {record.get('country_code')}  pop={record.get('population')}"
        )
        next_id += 1
    CATALOG_PATH.write_text(existing + "".join(additions), encoding="utf-8", newline="")
    return report


def _population(city: City, cache: dict) -> tuple[int | None, int | None]:
    """(population, geocoding id) — by stored id when there is one, by name otherwise.

    Name lookups return several records for one name and the populated prefecture is
    often not the first one (the bare "市" form can resolve to a village record with
    no population at all), so every candidate is collected and the most populated
    province-matched one wins.
    """
    if city.geocoding_id is not None:
        record = _by_id(city.geocoding_id, cache)
        return (record.get("population"), city.geocoding_id)
    terms = (f"{city.city}市", city.city, *EXTRA_TERMS.get(city.city, ()))
    candidates = []
    for term in terms:
        for item in _search(term, cache, country="CN"):
            if strip_suffix(item.get("name", "")) != city.city:
                continue
            if normalize_province(item.get("admin1", "")) != city.province:
                continue
            candidates.append(item)
    if not candidates:
        return (None, None)
    best = max(candidates, key=lambda item: item.get("population") or 0)
    return (best.get("population"), best.get("id"))


def elevation_profile(cities: list[City], cache: dict) -> dict[int, tuple[int, int] | None]:
    """Centre elevation and the five-point spread, batched 100 points a request."""
    offsets = ((0, 0), (RELIEF_OFFSET, 0), (-RELIEF_OFFSET, 0),
               (0, RELIEF_OFFSET), (0, -RELIEF_OFFSET))
    points: list[tuple[float, float]] = []
    spans: list[tuple[int, int]] = []
    for city in cities:
        start = len(points)
        for dlat, dlon in offsets:
            points.append((round(city.latitude + dlat, 4), round(city.longitude + dlon, 4)))
        spans.append((start, len(points)))

    values: list[float | None] = []
    for index in range(0, len(points), 100):  # the endpoint's own limit
        batch = points[index : index + 100]
        query = "&".join(f"latitude={lat}&longitude={lon}" for lat, lon in batch)
        payload = _fetch(f"{ELEVATION}?{query}", cache)
        values.extend(payload["elevation"])
        time.sleep(1.5)

    profile: dict[int, tuple[int, int] | None] = {}
    for city, (start, end) in zip(cities, spans, strict=True):
        window = values[start:end]
        if any(value is None for value in window):
            profile[city.location_id] = None
            continue
        numeric = [float(value) for value in window if value is not None]
        profile[city.location_id] = (
            int(round(numeric[0])),
            int(round(max(numeric) - min(numeric))),
        )
    return profile


def _synthetic(
    location_id: int, latitude: float, longitude: float, relief: int, population: int | None
) -> tuple[float, float, float]:
    """Roads, industry and the emission index they combine into.

    Deterministic per city so the file is reproducible. What the demo has to be able
    to explain is the belt it already draws — south-east coast clean, northern
    interior polluted — so the index is built from that belt and from city size,
    never from size alone (a first pass did exactly that and put Shanghai at the top
    and Lhasa at the bottom, the wrong way round for both PM2.5 and the narrative):

    - roads track population and flat ground (urban size and buildability);
    - industrial land tracks the inland/northern belt and flat ground;
    - the emission index is pressure (inland + heating demand) plus industrial land
      plus urban size, so 乌鲁木齐 and 唐山 land high and 拉萨 and 丽江 land low.

    ``relief`` is used as flatness, not as meteorology: a basin city like 成都 reads
    as flat here, and it is the per-city weather regime in the generator that makes
    it stagnant. This is a synthetic proxy and the CSV says so per row.
    """
    rng = random.Random(SYNTHETIC_SEED * 1000 + location_id)
    if population:
        pop_norm = min(1.0, max(0.0, math.log10(population / 2e5) / math.log10(2e7 / 2e5)))
    else:
        pop_norm = 0.4
    plainness = min(1.0, max(0.0, 1.0 - relief / 1500))
    inland = min(1.0, max(0.0, (latitude - 30.0) / 14.0)) * min(
        1.0, max(0.0, (113.0 - longitude) / 25.0)
    )
    heating = min(1.0, max(0.0, (latitude - 33.0) / 10.0))
    pressure = min(1.0, 0.55 * inland + 0.45 * heating)
    roads = 100 * min(1.0, 0.50 * pop_norm + 0.35 * plainness + 0.15 * rng.random())
    industry = min(1.0, 0.10 + 0.55 * pressure + 0.20 * plainness + 0.15 * rng.random())
    emission = 100 * min(
        1.0, 0.40 * pressure + 0.30 * industry + 0.15 * pop_norm + 0.15 * rng.random()
    )
    return (round(roads, 1), round(industry, 3), round(emission, 1))


def build_geography(cache: dict) -> list[str]:
    cities = read_catalog()
    profile = elevation_profile(cities, cache)
    report: list[str] = []
    rows: list[str] = []
    endpoint = ["location_id", "city", "province", "elevation_m", "relief_m", "population",
                "road_density_index", "industrial_share", "emission_intensity",
                "real_source", "synthetic_note"]
    rows.append(",".join(endpoint) + "\r\n")
    missing_population: list[str] = []
    for city in cities:
        population, _ = _population(city, cache)
        if population is None:
            missing_population.append(city.city)
        measurements = profile.get(city.location_id)
        if measurements is None:
            raise RuntimeError(f"{city.city}: no elevation returned")
        elevation, relief = measurements
        roads, industry, emission = _synthetic(
            city.location_id, city.latitude, city.longitude, relief, population
        )
        rows.append(
            f"{city.location_id},{city.city},{city.province},{elevation},{relief},"
            f"{population or ''},{roads},{industry},{emission},"
            f'"{REAL_SOURCE}","{SYNTHETIC_NOTE}"\r\n'
        )
    GEOGRAPHY_PATH.write_text("".join(rows), encoding="utf-8", newline="")
    report.append(
        f"  wrote {GEOGRAPHY_PATH.name}: {len(cities)} cities, "
        f"{len(cities) - len(missing_population)} with population"
    )
    report.append(
        f"  population missing ({len(missing_population)}): "
        f"{' '.join(missing_population) or '—'}"
    )
    return report


def main() -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    cache: dict[str, object] = (
        json.loads(CACHE_PATH.read_text(encoding="utf-8")) if CACHE_PATH.exists() else {}
    )
    try:
        print("repairing expanded coordinates")
        for line in repair_coordinates(cache):
            print(line)
        print("adding Hong Kong / Macao / Taiwan")
        for line in add_special_cities(cache):
            print(line)
        print("building geography")
        for line in build_geography(cache):
            print(line)
    finally:
        CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
