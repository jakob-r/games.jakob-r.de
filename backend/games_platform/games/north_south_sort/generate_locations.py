"""Generate ``locations.json`` for North South Sort from Wikidata (+ optional LLM curation).

Run from ``backend/``::

    uv run python -m games_platform.games.north_south_sort.generate_locations

Pipeline:
1. Candidate lists per Wikidata class (cheap queries: class + sitelink count only).
2. Details for the top candidates in batches (labels, coordinates, country, continent,
   area, extreme points, Wikipedia links).
3. Bounding boxes from extreme points, area, or a per-category default.
4. Optional LLM pass (OpenRouter, ``OPENROUTER_API_KEY``) that drops obscure or unsuitable
   entries, rates fame 1-5 and writes short en/de descriptions.
5. Continent-balanced selection, written sorted to ``locations.json``.

Wikidata responses and LLM answers are cached in ``backend/.cache/north_south_sort/`` so
reruns are cheap; pass ``--refresh`` to refetch from Wikidata.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import httpx

from games_platform.core.llm import LlmError, chat, llm_configured
from games_platform.games.north_south_sort.locations import (
    CATEGORIES,
    CONTINENTS,
    LOCATIONS_PATH,
    BoundsSource,
    Category,
    Continent,
    Location,
)

SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = "games.jakob-r.de location generator (https://github.com/jakob-r/games.jakob-r.de)"
CACHE_DIR = Path(__file__).resolve().parents[3] / ".cache" / "north_south_sort"

KM_PER_DEG = 111.0
DEFAULT_RADIUS_KM: dict[Category, float] = {"city": 5.0, "landmark": 0.5, "event": 2.0}
MAX_BOX_DEG = 10.0  # taller/wider boxes are data errors or too vague to play with
MAX_EVENT_LOCATION_KM2 = 50_000.0  # events "located" in a whole country are too vague

# (filter, minimum sitelinks). ``filter`` is a SPARQL triple pattern on ?item.
CANDIDATE_CLASSES: dict[Category, list[tuple[str, int]]] = {
    "city": [
        ("wdt:P31 wd:Q515", 25),  # city
        ("wdt:P31 wd:Q1549591", 20),  # big city
        ("wdt:P31 wd:Q1637706", 15),  # million city
        ("wdt:P31 wd:Q5119", 15),  # capital city
        ("wdt:P31 wd:Q200250", 15),  # metropolis
        ("wdt:P31 wd:Q1093829", 40),  # city in the United States
    ],
    "landmark": [
        ("wdt:P1435 wd:Q9259", 8),  # World Heritage Site
        ("wdt:P31 wd:Q570116", 15),  # tourist attraction
        ("wdt:P31 wd:Q4989906", 25),  # monument
        ("wdt:P31 wd:Q23413", 25),  # castle
        ("wdt:P31 wd:Q16560", 25),  # palace
        ("wdt:P31 wd:Q12518", 25),  # tower
        ("wdt:P31 wd:Q12280", 25),  # bridge
        ("wdt:P31 wd:Q839954", 25),  # archaeological site
        ("wdt:P31 wd:Q8502", 35),  # mountain
        ("wdt:P31 wd:Q8072", 35),  # volcano
        ("wdt:P31 wd:Q169358", 35),  # stratovolcano
        ("wdt:P31 wd:Q23397", 40),  # lake
        ("wdt:P31 wd:Q34038", 20),  # waterfall
        ("wdt:P31 wd:Q46169", 25),  # national park
        ("wdt:P31 wd:Q33506", 30),  # museum
        ("wdt:P31 wd:Q207694", 30),  # art museum
        ("wdt:P31 wd:Q16970", 30),  # church building
        ("wdt:P31 wd:Q2977", 25),  # cathedral
        ("wdt:P31 wd:Q44613", 25),  # monastery
        ("wdt:P31 wd:Q32815", 25),  # mosque
        ("wdt:P31 wd:Q44539", 25),  # temple
        ("wdt:P31 wd:Q57821", 25),  # fortification
        ("wdt:P31 wd:Q11303", 25),  # skyscraper
        ("wdt:P31 wd:Q35509", 20),  # cave
        ("wdt:P31 wd:Q150784", 20),  # canyon
        ("wdt:P31 wd:Q23442", 50),  # island
        ("wdt:P31 wd:Q1081138", 20),  # historic site
        ("wdt:P31 wd:Q483110", 35),  # stadium
        ("wdt:P31 wd:Q22698", 30),  # park
        ("wdt:P31 wd:Q174782", 25),  # square
    ],
    "event": [
        ("wdt:P31 wd:Q178561", 15),  # battle
        ("wdt:P31 wd:Q188055", 12),  # siege
        ("wdt:P31 wd:Q1261499", 12),  # naval battle
        ("wdt:P31 wd:Q645883", 12),  # military operation
        ("wdt:P31 wd:Q8065", 10),  # natural disaster
        ("wdt:P31 wd:Q7944", 10),  # earthquake
        ("wdt:P31 wd:Q7692360", 8),  # volcanic eruption
        ("wdt:P31 wd:Q3839081", 10),  # disaster
        ("wdt:P31 wd:Q3199915", 12),  # massacre
        ("wdt:P31 wd:Q2223653", 12),  # terrorist attack
        ("wdt:P31 wd:Q10931", 12),  # revolution
        ("wdt:P31 wd:Q124757", 12),  # riot
        ("wdt:P31 wd:Q13418847", 10),  # historical event
        ("wdt:P31 wd:Q159821", 10),  # Summer Olympic Games
        ("wdt:P31 wd:Q82414", 10),  # Winter Olympic Games
        ("wdt:P31 wd:Q131569", 15),  # treaty (located at its signing place)
    ],
}
CANDIDATE_LIMIT = 2500

CONTINENT_QIDS: dict[str, Continent] = {
    "Q46": "europe",
    "Q48": "asia",
    "Q15": "africa",
    "Q49": "north_america",
    "Q18": "south_america",
    "Q55643": "oceania",
    "Q538": "oceania",
    "Q3960": "oceania",
    "Q51": "antarctica",
}
EURASIA = "Q5401"
AMERICAS = "Q828"


# --------------------------------------------------------------------------- data model


@dataclass(slots=True)
class Candidate:
    id: str
    category: Category
    sitelinks: int
    name_en: str | None = None
    name_de: str | None = None
    desc_en: str | None = None
    desc_de: str | None = None
    lat: float | None = None
    lon: float | None = None
    area_km2: float | None = None
    location_area_km2: float | None = None
    extremes: dict[str, tuple[float, float]] = field(default_factory=dict)
    country_id: str | None = None
    country_en: str | None = None
    country_de: str | None = None
    item_continents: set[str] = field(default_factory=set)
    country_continents: set[str] = field(default_factory=set)
    wikipedia_en: str | None = None
    wikipedia_de: str | None = None
    continent: Continent | None = None


@dataclass(slots=True)
class Curation:
    keep: bool
    fame: int
    description_en: str
    description_de: str
    name_de: str | None = None


# --------------------------------------------------------------------------- pure helpers

_POINT_RE = re.compile(r"Point\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)")


def parse_point(wkt: str | None) -> tuple[float, float] | None:
    """Parse a Wikidata ``Point(lon lat)`` literal into ``(lat, lon)``."""
    if not wkt:
        return None
    match = _POINT_RE.search(wkt)
    if not match:
        return None
    lon, lat = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def qid(uri: str | None) -> str | None:
    if not uri:
        return None
    return uri.rsplit("/", 1)[-1]


def _km_to_lon_deg(km: float, lat: float) -> float:
    return km / (KM_PER_DEG * max(math.cos(math.radians(lat)), 0.05))


def approximate_bounds(
    lat: float,
    lon: float,
    category: Category,
    area_km2: float | None = None,
    extremes: dict[str, tuple[float, float]] | None = None,
) -> tuple[float, float, float, float, BoundsSource]:
    """Return ``(min_lat, max_lat, min_lon, max_lon, source)`` around the center.

    ``extremes`` maps ``north``/``south``/``east``/``west`` to ``(lat, lon)`` points.
    Missing sides come from the area (as a square) or the category default radius, which
    is also the minimum size.
    The center always lies inside, and boxes larger than ``MAX_BOX_DEG`` fall back.
    """
    if area_km2 and math.sqrt(area_km2) / 2 > DEFAULT_RADIUS_KM[category]:
        half_km = math.sqrt(area_km2) / 2
        source: BoundsSource = "area"
    else:
        half_km = DEFAULT_RADIUS_KM[category]
        source = "default"
    d_lat = half_km / KM_PER_DEG
    d_lon = _km_to_lon_deg(half_km, lat)
    min_lat, max_lat, min_lon, max_lon = lat - d_lat, lat + d_lat, lon - d_lon, lon + d_lon

    extremes = extremes or {}
    if extremes:
        source = "extreme_points"
        if "north" in extremes:
            max_lat = extremes["north"][0]
        if "south" in extremes:
            min_lat = extremes["south"][0]
        if "east" in extremes:
            max_lon = extremes["east"][1]
        if "west" in extremes:
            min_lon = extremes["west"][1]

    min_lat, max_lat = min(min_lat, lat), max(max_lat, lat)
    min_lon, max_lon = min(min_lon, lon), max(max_lon, lon)

    if max_lat - min_lat > MAX_BOX_DEG or max_lon - min_lon > MAX_BOX_DEG:
        if source == "default":  # pragma: no cover - default radii are tiny
            raise ValueError("default radius too large")
        return approximate_bounds(lat, lon, category)

    min_lat, max_lat = max(min_lat, -90.0), min(max_lat, 90.0)
    min_lon, max_lon = max(min_lon, -180.0), min(max_lon, 180.0)
    # Round outwards so the (separately rounded) center always stays inside.
    return (
        math.floor(min_lat * 1e4) / 1e4,
        math.ceil(max_lat * 1e4) / 1e4,
        math.floor(min_lon * 1e4) / 1e4,
        math.ceil(max_lon * 1e4) / 1e4,
        source,
    )


def _split_two(lat: float, lon: float, a: Continent, b: Continent) -> Continent | None:
    pair = {a, b}
    if pair == {"europe", "asia"}:
        # Ural (≈60°E), Caucasus, and the Bosporus / Black Sea south coast.
        caucasus = lon > 41 and lat < 44.5
        anatolia = lon > 29.1 and lat < 42
        europe = lon < 60 and lat > 36 and not caucasus and not anatolia
        return "europe" if europe else "asia"
    if pair == {"africa", "asia"}:
        return "asia" if lon > 32.3 and lat > 27.7 else "africa"
    if pair == {"north_america", "south_america"}:
        return "south_america" if lat < 8.5 and lon > -77.4 else "north_america"
    if pair == {"asia", "oceania"}:
        return "oceania" if lon > 130 and lat < 0 else "asia"
    return None


def pick_continent(lat: float, lon: float, continent_qids: set[str]) -> Continent | None:
    """Map Wikidata continent QIDs to one continent slug, splitting transcontinental cases."""
    slugs: set[Continent] = set()
    for c in continent_qids:
        if c in CONTINENT_QIDS:
            slugs.add(CONTINENT_QIDS[c])
        elif c == EURASIA:
            slugs |= {"europe", "asia"}
        elif c == AMERICAS:
            slugs |= {"north_america", "south_america"}
    if not slugs:
        return None
    ordered = [c for c in CONTINENTS if c in slugs]
    if len(ordered) == 1:
        return ordered[0]
    for i, a in enumerate(ordered):
        for b in ordered[i + 1 :]:
            split = _split_two(lat, lon, a, b)
            if split is not None:
                return split
    return ordered[0]


def fame_from_sitelinks(sitelinks: int) -> int:
    for threshold, fame in ((150, 5), (80, 4), (40, 3), (20, 2)):
        if sitelinks >= threshold:
            return fame
    return 1


def select_balanced[T](
    items: list[T],
    total: int,
    continent_of,
    floor: int,
) -> list[T]:
    """Pick ``total`` items from ``items`` (already sorted best first).

    Every continent first gets up to ``floor`` of its best items, then the remaining
    slots go to the best leftover items regardless of continent.
    """
    by_continent: dict[str, list[T]] = defaultdict(list)
    for item in items:
        by_continent[continent_of(item)].append(item)
    chosen_ids: set[int] = set()
    chosen: list[T] = []
    for group in by_continent.values():
        for item in group[:floor]:
            chosen_ids.add(id(item))
            chosen.append(item)
    if len(chosen) > total:  # floors alone overflow: keep the globally best
        order = {id(item): i for i, item in enumerate(items)}
        chosen.sort(key=lambda item: order[id(item)])
        return chosen[:total]
    for item in items:
        if len(chosen) >= total:
            break
        if id(item) not in chosen_ids:
            chosen_ids.add(id(item))
            chosen.append(item)
    order = {id(item): i for i, item in enumerate(items)}
    chosen.sort(key=lambda item: order[id(item)])
    return chosen


def apply_detail_rows(candidates: dict[str, Candidate], rows: list[dict]) -> None:
    """Merge raw SPARQL detail bindings into the candidates (first value wins)."""

    def val(row: dict, key: str) -> str | None:
        cell = row.get(key)
        return cell["value"] if cell else None

    country_prio: dict[str, int] = {}
    for row in rows:
        cand = candidates.get(qid(val(row, "item")) or "")
        if cand is None:
            continue
        cand.name_en = cand.name_en or val(row, "labelEn")
        cand.name_de = cand.name_de or val(row, "labelDe")
        cand.desc_en = cand.desc_en or val(row, "descEn")
        cand.desc_de = cand.desc_de or val(row, "descDe")
        cand.wikipedia_en = cand.wikipedia_en or val(row, "enwiki")
        cand.wikipedia_de = cand.wikipedia_de or val(row, "dewiki")
        if cand.lat is None:
            point = parse_point(val(row, "coord"))
            if point is None:
                point = parse_point(val(row, "locCoord"))
                if point is not None and val(row, "locArea"):
                    cand.location_area_km2 = float(val(row, "locArea")) / 1e6
            if point is not None:
                cand.lat, cand.lon = point
        if cand.area_km2 is None and val(row, "area"):
            area = float(val(row, "area")) / 1e6
            cand.area_km2 = area if area > 0 else None
        for side in ("north", "south", "east", "west"):
            point = parse_point(val(row, side))
            if point is not None and side not in cand.extremes:
                cand.extremes[side] = point
        if c := qid(val(row, "itemContinent")):
            cand.item_continents.add(c)
        country = qid(val(row, "country"))
        if country:
            # Prefer the item's own country, then current sovereign states with a continent
            # over historical states.
            prio = (
                (4 if val(row, "ownCountry") else 0)
                + (2 if val(row, "sovereign") else 0)
                + (1 if val(row, "countryContinent") else 0)
            )
            if prio > country_prio.get(cand.id, -1):
                country_prio[cand.id] = prio
                cand.country_id = country
                cand.country_en = val(row, "countryEn")
                cand.country_de = val(row, "countryDe")
                cand.country_continents = set()
            if country == cand.country_id and (c := qid(val(row, "countryContinent"))):
                cand.country_continents.add(c)


def finalize_candidate(cand: Candidate) -> str | None:
    """Fill ``continent``; return a reason string if the candidate is unusable."""
    if not cand.name_en or re.fullmatch(r"Q\d+", cand.name_en):
        return "no English label"
    if cand.lat is None or cand.lon is None:
        return "no coordinates"
    if not cand.wikipedia_en:
        return "no English Wikipedia article"
    if (
        cand.category == "event"
        and cand.location_area_km2 is not None
        and cand.location_area_km2 > MAX_EVENT_LOCATION_KM2
    ):
        return "event location too large"
    cand.continent = pick_continent(
        cand.lat, cand.lon, cand.item_continents or cand.country_continents
    )
    if cand.continent is None:
        return "no continent"
    return None


def parse_llm_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("no JSON object in answer")
    return json.loads(text[start : end + 1])


# --------------------------------------------------------------------------- Wikidata


class WikidataError(RuntimeError):
    pass


class Wikidata:
    def __init__(self, client: httpx.AsyncClient, *, refresh: bool) -> None:
        self.client = client
        self.refresh = refresh
        self.cache_dir = CACHE_DIR / "sparql"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._last_request = 0.0

    async def query(self, sparql: str, *, attempts: int = 4) -> list[dict]:
        """Run a query, cached on disk per query text.

        ``attempts`` limits retries after server errors/timeouts (a slow query usually
        stays slow, so batch callers pass 1 and split instead). Rate limits (429) and
        connection problems are always retried with backoff.
        """
        key = hashlib.sha1(sparql.encode()).hexdigest()
        path = self.cache_dir / f"{key}.json"
        if path.exists() and not self.refresh:
            return json.loads(path.read_text())
        failures = 0
        for transient in range(8):
            wait = 1.0 - (time.monotonic() - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()
            delay = 0.0
            try:
                response = await self.client.post(
                    SPARQL_URL,
                    data={"query": sparql},
                    headers={"Accept": "application/sparql-results+json"},
                )
                if response.status_code == 200:
                    rows = response.json()["results"]["bindings"]
                    path.write_text(json.dumps(rows))
                    return rows
                error = f"HTTP {response.status_code}"
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    delay = float(retry_after)
                is_timeout = response.status_code != 429
            except httpx.TimeoutException as e:
                error, is_timeout = repr(e), True
            except (httpx.HTTPError, ValueError) as e:
                error, is_timeout = repr(e), False
            if is_timeout:
                failures += 1
                if failures >= attempts:
                    break
            delay = max(delay, 5 * 2 ** min(transient, 5))
            print(f"  Wikidata query failed ({error}), retrying in {delay:.0f}s", file=sys.stderr)
            await asyncio.sleep(delay)
        raise WikidataError(f"Wikidata query kept failing ({error})")

    async def candidates(self, category: Category) -> dict[str, int]:
        found: dict[str, int] = {}
        for pattern, min_sitelinks in CANDIDATE_CLASSES[category]:
            sparql = (
                f"SELECT ?item ?sl WHERE {{ ?item {pattern} ; wikibase:sitelinks ?sl . "
                f"FILTER(?sl >= {min_sitelinks}) }} ORDER BY DESC(?sl) LIMIT {CANDIDATE_LIMIT}"
            )
            rows = await self.query(sparql)
            for row in rows:
                item = qid(row["item"]["value"])
                if item:
                    found[item] = max(found.get(item, 0), int(row["sl"]["value"]))
            print(f"  {category}: {pattern} → {len(rows)} (total {len(found)})")
        return found

    async def details(self, ids: list[str]) -> list[dict]:
        """Fetch detail rows; a batch that keeps timing out is split in halves.

        Items with many coordinates/countries multiply the result rows, which can make a
        whole batch time out. A single item that still fails is skipped.
        """
        try:
            return await self._details(ids)
        except WikidataError:
            if len(ids) == 1:
                print(f"  skipping {ids[0]}: details query keeps failing", file=sys.stderr)
                return []
            mid = len(ids) // 2
            return await self.details(ids[:mid]) + await self.details(ids[mid:])

    async def _details(self, ids: list[str]) -> list[dict]:
        values = " ".join(f"wd:{i}" for i in ids)
        sparql = f"""
SELECT * WHERE {{
  VALUES ?item {{ {values} }}
  OPTIONAL {{ ?item rdfs:label ?labelEn FILTER(LANG(?labelEn) = "en") }}
  OPTIONAL {{ ?item rdfs:label ?labelDe FILTER(LANG(?labelDe) = "de") }}
  OPTIONAL {{ ?item schema:description ?descEn FILTER(LANG(?descEn) = "en") }}
  OPTIONAL {{ ?item schema:description ?descDe FILTER(LANG(?descDe) = "de") }}
  OPTIONAL {{ ?item wdt:P625 ?coord }}
  OPTIONAL {{
    ?item wdt:P276|wdt:P1071 ?loc . ?loc wdt:P625 ?locCoord .
    OPTIONAL {{ ?loc p:P2046/psn:P2046/wikibase:quantityAmount ?locArea }}
  }}
  # Country lookups stay inside the block that binds ?country: an unbound ?country in
  # a separate OPTIONAL would match every label in Wikidata and time out.
  OPTIONAL {{
    {{ ?item wdt:P17 ?country . BIND(true AS ?ownCountry) }}
    UNION {{ ?item wdt:P276|wdt:P1071 ?countryLoc . ?countryLoc wdt:P17 ?country }}
    OPTIONAL {{ ?country rdfs:label ?countryEn FILTER(LANG(?countryEn) = "en") }}
    OPTIONAL {{ ?country rdfs:label ?countryDe FILTER(LANG(?countryDe) = "de") }}
    OPTIONAL {{ ?country wdt:P30 ?countryContinent }}
    OPTIONAL {{ ?country wdt:P31 wd:Q3624078 . BIND(true AS ?sovereign) }}
  }}
  OPTIONAL {{ ?item wdt:P30 ?itemContinent }}
  OPTIONAL {{ ?item p:P2046/psn:P2046/wikibase:quantityAmount ?area }}
  OPTIONAL {{ ?item wdt:P1332 ?north }}
  OPTIONAL {{ ?item wdt:P1333 ?south }}
  OPTIONAL {{ ?item wdt:P1334 ?east }}
  OPTIONAL {{ ?item wdt:P1335 ?west }}
  OPTIONAL {{ ?enwiki schema:about ?item ; schema:isPartOf <https://en.wikipedia.org/> }}
  OPTIONAL {{ ?dewiki schema:about ?item ; schema:isPartOf <https://de.wikipedia.org/> }}
}}"""
        return await self.query(sparql, attempts=1 if len(ids) > 1 else 2)


# --------------------------------------------------------------------------- LLM curation

LLM_BATCH = 25
LLM_CONCURRENCY = 4
LLM_TIMEOUT = httpx.Timeout(180.0, connect=10.0)

CATEGORY_HINTS: dict[Category, str] = {
    "city": "cities",
    "landmark": "landmarks, famous sights and natural wonders",
    "event": "historical events tied to one specific place",
}


def build_llm_messages(category: Category, batch: list[Candidate]) -> list[dict]:
    items = [
        {
            "id": c.id,
            "name": c.name_en,
            "name_de": c.name_de,
            "country": c.country_en,
            "wikidata_description": c.desc_en,
        }
        for c in batch
    ]
    system = (
        "You curate locations for a geography party game. Players see a location's name "
        "and must guess whether it lies north or south of other locations. "
        f"This batch contains candidate {CATEGORY_HINTS[category]}.\n"
        "For every item return:\n"
        '- "keep": true only if a typical educated adult in Europe or America has a fair '
        "chance of having heard of it and it is a real, single place (for events: the event "
        "happened at one clearly defined place, not across a whole country or a war). "
        "Drop duplicates of the same place, generic or technical entries, and disputed or "
        "offensive ones.\n"
        '- "fame": 1 (obscure) to 5 (world famous).\n'
        '- "description_en" and "description_de": one short sentence (max 15 words) that '
        "says what it is or what happened. Never mention coordinates, compass directions, "
        "or words like north/south/northernmost, and do not repeat the name.\n"
        '- "name_de": the usual German name (same as English if there is none).\n'
        'Answer with one JSON object mapping each id to its object, e.g. {"Q64": {"keep": '
        'true, "fame": 5, "description_en": "...", "description_de": "...", "name_de": '
        '"Berlin"}}. No other text.'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(items, ensure_ascii=False)},
    ]


class Curator:
    def __init__(self) -> None:
        self.path = CACHE_DIR / "llm.json"
        self.cache: dict[str, dict] = (
            json.loads(self.path.read_text()) if self.path.exists() else {}
        )
        self.semaphore = asyncio.Semaphore(LLM_CONCURRENCY)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=1))

    async def _batch(self, category: Category, batch: list[Candidate]) -> None:
        async with self.semaphore:
            for attempt in range(2):
                try:
                    raw = await chat(
                        build_llm_messages(category, batch),
                        max_tokens=150 * len(batch),
                        timeout=LLM_TIMEOUT,
                    )
                    answer = parse_llm_json(raw)
                except (LlmError, ValueError) as e:
                    print(f"  LLM batch failed (attempt {attempt + 1}): {e!r}", file=sys.stderr)
                    continue
                for cand in batch:
                    entry = answer.get(cand.id)
                    if isinstance(entry, dict) and "keep" in entry:
                        self.cache[f"{category}:{cand.id}"] = entry
                self.save()
                return

    async def curate(self, category: Category, cands: list[Candidate]) -> dict[str, Curation]:
        todo = [c for c in cands if f"{category}:{c.id}" not in self.cache]
        batches = [todo[i : i + LLM_BATCH] for i in range(0, len(todo), LLM_BATCH)]
        if batches:
            print(f"  LLM: {len(todo)} {category} candidates in {len(batches)} batches")
        await asyncio.gather(*(self._batch(category, b) for b in batches))
        result: dict[str, Curation] = {}
        for cand in cands:
            entry = self.cache.get(f"{category}:{cand.id}")
            if entry is None:
                continue
            try:
                fame = min(5, max(1, int(entry.get("fame", 1))))
            except (TypeError, ValueError):
                fame = 1
            result[cand.id] = Curation(
                keep=bool(entry.get("keep")),
                fame=fame,
                description_en=str(entry.get("description_en") or "").strip(),
                description_de=str(entry.get("description_de") or "").strip(),
                name_de=(str(entry.get("name_de")).strip() or None)
                if entry.get("name_de")
                else None,
            )
        return result


# --------------------------------------------------------------------------- main


def to_location(cand: Candidate, curation: Curation | None) -> Location:
    assert cand.lat is not None and cand.lon is not None and cand.continent is not None
    min_lat, max_lat, min_lon, max_lon, source = approximate_bounds(
        cand.lat, cand.lon, cand.category, cand.area_km2, cand.extremes
    )
    if curation is not None:
        fame = curation.fame
        desc_en = curation.description_en or cand.desc_en or ""
        desc_de = curation.description_de or cand.desc_de or desc_en
        name_de = cand.name_de or curation.name_de or cand.name_en
    else:
        fame = fame_from_sitelinks(cand.sitelinks)
        desc_en = cand.desc_en or ""
        desc_de = cand.desc_de or desc_en
        name_de = cand.name_de or cand.name_en
    assert cand.name_en and cand.wikipedia_en and name_de
    return Location(
        id=cand.id,
        category=cand.category,
        name_en=cand.name_en,
        name_de=name_de,
        lat=round(cand.lat, 5),
        lon=round(cand.lon, 5),
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
        bounds_source=source,
        description_en=desc_en,
        description_de=desc_de,
        wikipedia_en=cand.wikipedia_en,
        wikipedia_de=cand.wikipedia_de,
        country_en=cand.country_en,
        country_de=cand.country_de,
        continent=cand.continent,
        fame=fame,
        sitelinks=cand.sitelinks,
    )


def score(cand: Candidate, curations: dict[str, Curation]) -> tuple[int, int]:
    cur = curations.get(cand.id)
    return (cur.fame if cur else fame_from_sitelinks(cand.sitelinks), cand.sitelinks)


def print_summary(locations: list[Location]) -> None:
    counts = Counter((loc.category, loc.continent) for loc in locations)
    header = f"{'':10}" + "".join(f"{c[:9]:>10}" for c in CONTINENTS) + f"{'total':>8}"
    print(header)
    for cat in CATEGORIES:
        row = [counts[(cat, cont)] for cont in CONTINENTS]
        print(f"{cat:10}" + "".join(f"{n:>10}" for n in row) + f"{sum(row):>8}")
    print("bounds:", dict(Counter(loc.bounds_source for loc in locations)))


async def run(args: argparse.Namespace) -> None:
    categories: list[Category] = [args.only] if args.only else list(CATEGORIES)
    use_llm = not args.no_llm and llm_configured()
    if not args.no_llm and not use_llm:
        print("OPENROUTER_API_KEY not set: skipping LLM curation", file=sys.stderr)
    pre_llm = math.ceil(args.per_category * 1.5)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(90.0, connect=10.0), headers={"User-Agent": USER_AGENT}
    ) as client:
        wikidata = Wikidata(client, refresh=args.refresh)
        seen: set[str] = set()
        locations: list[Location] = []
        curator = Curator() if use_llm else None

        # City before landmark before event: an item found in several keeps the first.
        for category in CATEGORIES:
            print(f"[{category}] fetching candidates")
            sitelinks = await wikidata.candidates(category)
            if category not in categories:
                seen |= set(sitelinks)
                continue
            ranked = [q for q in sorted(sitelinks, key=lambda q: -sitelinks[q]) if q not in seen]
            seen |= set(sitelinks)
            cands = {q: Candidate(id=q, category=category, sitelinks=sitelinks[q]) for q in ranked}
            print(f"[{category}] fetching details for {len(ranked)} items")
            for i in range(0, len(ranked), 100):
                apply_detail_rows(cands, await wikidata.details(ranked[i : i + 100]))
                print(f"  details {min(i + 100, len(ranked))}/{len(ranked)}")
            reasons: Counter[str] = Counter()
            usable: list[Candidate] = []
            for q in ranked:
                reason = finalize_candidate(cands[q])
                if reason:
                    reasons[reason] += 1
                else:
                    usable.append(cands[q])
            print(f"[{category}] usable {len(usable)}, dropped {dict(reasons)}")

            shortlist = select_balanced(
                usable, pre_llm, lambda c: c.continent, floor=args.floor * 3 // 2
            )
            curations: dict[str, Curation] = {}
            if curator is not None:
                # The LLM drops a lot of some categories (events): widen the shortlist until
                # enough survive or the usable candidates run out.
                size = pre_llm
                while True:
                    curations = await curator.curate(category, shortlist)
                    kept = [c for c in shortlist if c.id not in curations or curations[c.id].keep]
                    print(
                        f"[{category}] LLM rated {len(curations)}, kept {len(kept)} "
                        f"of {len(shortlist)} shortlisted"
                    )
                    if len(kept) >= args.per_category or len(shortlist) >= len(usable):
                        break
                    size += 2 * (args.per_category - len(kept))
                    shortlist = select_balanced(
                        usable, size, lambda c: c.continent, floor=args.floor * 3 // 2
                    )
                shortlist = kept

            shortlist.sort(key=lambda c, cur=curations: score(c, cur), reverse=True)
            chosen = select_balanced(
                shortlist, args.per_category, lambda c: c.continent, floor=args.floor
            )
            locations.extend(to_location(c, curations.get(c.id)) for c in chosen)

    if args.only and args.output.exists():
        previous = json.loads(args.output.read_text(encoding="utf-8"))["locations"]
        locations.extend(Location.from_dict(d) for d in previous if d["category"] != args.only)

    locations.sort(key=lambda loc: (CATEGORIES.index(loc.category), int(loc.id[1:])))
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source": "Wikidata (CC0)" + (" + LLM curation" if use_llm else ""),
        "locations": [asdict(loc) for loc in locations],
    }
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n")
    print(f"wrote {len(locations)} locations to {args.output}")
    print_summary(locations)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--per-category", type=int, default=1000)
    parser.add_argument(
        "--floor", type=int, default=80, help="minimum per continent and category if available"
    )
    parser.add_argument("--only", choices=CATEGORIES, help="regenerate one category only")
    parser.add_argument("--no-llm", action="store_true", help="skip the LLM curation pass")
    parser.add_argument("--refresh", action="store_true", help="ignore the Wikidata cache")
    parser.add_argument("--output", type=Path, default=LOCATIONS_PATH)
    sys.stdout.reconfigure(line_buffering=True)  # progress shows up live in logs
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
