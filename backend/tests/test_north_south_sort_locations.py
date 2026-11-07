from collections import Counter

import pytest

from games_platform.games.north_south_sort.generate_locations import (
    Candidate,
    apply_detail_rows,
    approximate_bounds,
    finalize_candidate,
    parse_llm_json,
    parse_point,
    pick_continent,
    select_balanced,
)
from games_platform.games.north_south_sort.locations import (
    CATEGORIES,
    CONTINENTS,
    LOCATIONS_PATH,
    load_locations,
)


def test_parse_point():
    assert parse_point("Point(13.38 52.52)") == (52.52, 13.38)
    assert parse_point("Point(-0.1 -1e1)") == (-10.0, -0.1)
    assert parse_point("garbage") is None
    assert parse_point("Point(500 10)") is None


def test_bounds_default_and_area():
    min_lat, max_lat, min_lon, max_lon, source = approximate_bounds(50.0, 10.0, "landmark")
    assert source == "default"
    assert min_lat < 50.0 < max_lat and min_lon < 10.0 < max_lon
    assert max_lat - min_lat == pytest.approx(1 / 111, abs=1e-3)

    min_lat, max_lat, min_lon, max_lon, source = approximate_bounds(
        0.0, 0.0, "city", area_km2=400.0
    )
    assert source == "area"
    assert max_lat - min_lat == pytest.approx(20 / 111, abs=1e-3)


def test_bounds_widen_longitude_near_poles():
    _, _, min_lon_eq, max_lon_eq, _ = approximate_bounds(0.0, 0.0, "city")
    _, _, min_lon_n, max_lon_n, _ = approximate_bounds(70.0, 0.0, "city")
    assert max_lon_n - min_lon_n > 2 * (max_lon_eq - min_lon_eq)


def test_bounds_extreme_points_keep_center_inside():
    extremes = {"north": (55.0, 10.0), "south": (47.3, 10.0), "east": (51.0, 15.0)}
    min_lat, max_lat, min_lon, max_lon, source = approximate_bounds(
        51.0, 10.0, "landmark", extremes=extremes
    )
    assert source == "extreme_points"
    assert (min_lat, max_lat, max_lon) == (47.3, 55.0, 15.0)
    assert min_lon <= 10.0

    # Extreme point on the wrong side of the center is ignored for that side.
    min_lat, max_lat, *_ = approximate_bounds(
        51.0, 10.0, "landmark", extremes={"north": (40.0, 10.0)}
    )
    assert min_lat <= 51.0 <= max_lat


def test_bounds_never_smaller_than_default():
    *_, source = approximate_bounds(0.0, 0.0, "city", area_km2=1.0)
    assert source == "default"


def test_bounds_round_outwards():
    lat, lon = 58.01389, 56.248888
    min_lat, max_lat, min_lon, max_lon, _ = approximate_bounds(
        lat, lon, "city", extremes={"west": (lat, lon)}
    )
    assert min_lon <= round(lon, 5) <= max_lon
    assert min_lat <= round(lat, 5) <= max_lat


def test_bounds_too_large_fall_back_to_default():
    *_, source = approximate_bounds(0.0, 0.0, "landmark", area_km2=5_000_000.0)
    assert source == "default"


def test_pick_continent():
    assert pick_continent(52.5, 13.4, {"Q46"}) == "europe"
    assert pick_continent(-33.9, 151.2, {"Q538"}) == "oceania"
    # Russia: Moscow in Europe, Vladivostok in Asia.
    assert pick_continent(55.75, 37.6, {"Q46", "Q48"}) == "europe"
    assert pick_continent(43.1, 131.9, {"Q46", "Q48"}) == "asia"
    # Turkey: Istanbul (European side) vs Ankara.
    assert pick_continent(41.01, 28.97, {"Q46", "Q48"}) == "europe"
    assert pick_continent(39.93, 32.86, {"Q46", "Q48"}) == "asia"
    # Egypt: Cairo vs Sharm el-Sheikh.
    assert pick_continent(30.04, 31.24, {"Q15", "Q48"}) == "africa"
    assert pick_continent(27.9, 34.33, {"Q15", "Q48"}) == "asia"
    assert pick_continent(0.0, 0.0, {"Q123"}) is None


def test_select_balanced_floor_and_total():
    items = [("europe", i) for i in range(10)] + [("africa", i) for i in range(3)]
    chosen = select_balanced(items, 6, lambda x: x[0], floor=2)
    assert len(chosen) == 6
    assert sum(1 for c in chosen if c[0] == "africa") == 2
    # Original order is kept.
    assert chosen == sorted(chosen, key=items.index)

    assert len(select_balanced(items, 100, lambda x: x[0], floor=2)) == len(items)
    assert len(select_balanced(items, 3, lambda x: x[0], floor=5)) == 3


def _b(value: str) -> dict:
    return {"value": value}


def test_apply_detail_rows_prefers_sovereign_country():
    cand = Candidate(id="Q1", category="event", sitelinks=30)
    rows = [
        {
            "item": _b("http://www.wikidata.org/entity/Q1"),
            "labelEn": _b("Battle of Somewhere"),
            "locCoord": _b("Point(10 50)"),
            "locArea": _b("2000000"),
            "country": _b("http://www.wikidata.org/entity/Q27306"),
            "countryEn": _b("Kingdom of Prussia"),
        },
        {
            "item": _b("http://www.wikidata.org/entity/Q1"),
            "country": _b("http://www.wikidata.org/entity/Q183"),
            "ownCountry": _b("true"),
            "countryEn": _b("Germany"),
            "countryDe": _b("Deutschland"),
            "countryContinent": _b("http://www.wikidata.org/entity/Q46"),
            "sovereign": _b("true"),
            "enwiki": _b("https://en.wikipedia.org/wiki/Battle_of_Somewhere"),
        },
        {  # a sovereign country reached via the location loses against the own country
            "item": _b("http://www.wikidata.org/entity/Q1"),
            "country": _b("http://www.wikidata.org/entity/Q142"),
            "countryEn": _b("France"),
            "countryContinent": _b("http://www.wikidata.org/entity/Q46"),
            "sovereign": _b("true"),
        },
        {"item": _b("http://www.wikidata.org/entity/Q999"), "labelEn": _b("ignored")},
    ]
    apply_detail_rows({"Q1": cand}, rows)
    assert (cand.lat, cand.lon) == (50.0, 10.0)
    assert cand.location_area_km2 == pytest.approx(2.0)
    assert cand.country_en == "Germany" and cand.country_de == "Deutschland"
    assert finalize_candidate(cand) is None
    assert cand.continent == "europe"


def test_finalize_candidate_reasons():
    cand = Candidate(id="Q2", category="city", sitelinks=10, name_en="Q2")
    assert finalize_candidate(cand) == "no English label"
    cand.name_en = "Town"
    assert finalize_candidate(cand) == "no coordinates"


def test_parse_llm_json():
    assert parse_llm_json('```json\n{"Q1": {"keep": true}}\n```') == {"Q1": {"keep": True}}
    with pytest.raises(ValueError):
        parse_llm_json("nope")


@pytest.mark.skipif(not LOCATIONS_PATH.exists(), reason="locations.json not generated yet")
def test_committed_locations_are_valid():
    locations = load_locations()
    ids = [loc.id for loc in locations]
    assert len(ids) == len(set(ids))
    per_category = Counter(loc.category for loc in locations)
    for category in CATEGORIES:
        assert per_category[category] >= 900
    for loc in locations:
        assert loc.category in CATEGORIES
        assert loc.continent in CONTINENTS
        assert loc.min_lat <= loc.lat <= loc.max_lat
        assert loc.min_lon <= loc.lon <= loc.max_lon
        assert 1 <= loc.fame <= 5
        assert loc.name_en and loc.name_de and loc.description_en
        assert loc.wikipedia_en.startswith("https://en.wikipedia.org/")
