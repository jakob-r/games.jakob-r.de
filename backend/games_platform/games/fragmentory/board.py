"""Pure board logic for Fragmentory (square cards with separation lines on an infinite grid).

Geometry
--------
Each card side is split into two half-edges, numbered clockwise starting at the top-left:

    0 1          N side: 0 = west half, 1 = east half
  7     2        E side: 2 = north half, 3 = south half
  6     3        S side: 4 = east half, 5 = west half
    5 4          W side: 6 = south half, 7 = north half

An *area* of a card is the set of half-edges it touches. A side with a line has its two
halves in different areas (except for the line ending, whose stub does not separate). Rotating
a card by one quarter turn clockwise maps half-edge ``h`` to ``(h + 2) % 8`` and side ``s`` to
``(s + 1) % 4``.

Areas of neighbouring cards that share a half-edge join into one *region*. A region's colour
comes from the owners of its areas: none (white), one player, or several (gray: a tie that has
not been resolved yet).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

type Cells = dict[str, dict[str, Any]]
type AreaRef = tuple[str, int]

GRAY = "gray"

SIDE_OFFSETS: tuple[tuple[int, int], ...] = ((-1, 0), (0, 1), (1, 0), (0, -1))  # N E S W

# Base orientation of every card type: sides with a line and the areas (as half-edge sets).
CARD_TYPES: dict[str, dict[str, Any]] = {
    "straight": {"lines": (0, 2), "areas": ((1, 2, 3, 4), (5, 6, 7, 0))},
    "curve": {"lines": (0, 1), "areas": ((1, 2), (3, 4, 5, 6, 7, 0))},
    "cross": {"lines": (0, 1, 2, 3), "areas": ((1, 2), (3, 4), (5, 6), (7, 0))},
    "t": {"lines": (1, 2, 3), "areas": ((7, 0, 1, 2), (3, 4), (5, 6))},
    "end": {"lines": (0,), "areas": ((0, 1, 2, 3, 4, 5, 6, 7),)},
}

DECK_COUNTS: dict[str, int] = {"straight": 6, "curve": 12, "cross": 6, "t": 10, "end": 4}


def cell_key(row: int, col: int) -> str:
    return f"{row},{col}"


def parse_key(key: str) -> tuple[int, int]:
    r, c = key.split(",")
    return int(r), int(c)


def card_lines(card_type: str, rot: int) -> set[int]:
    return {(s + rot) % 4 for s in CARD_TYPES[card_type]["lines"]}


def card_areas(card_type: str, rot: int) -> list[list[int]]:
    return [[(h + 2 * rot) % 8 for h in area] for area in CARD_TYPES[card_type]["areas"]]


def half_to_area(card_type: str, rot: int) -> list[int]:
    out = [0] * 8
    for idx, area in enumerate(card_areas(card_type, rot)):
        for h in area:
            out[h] = idx
    return out


def neighbor_half(h: int) -> tuple[int, int, int]:
    """Offset to the neighbouring cell and the half-edge there that touches ``h``."""
    side = h // 2
    opposite = (side + 2) % 4
    dr, dc = SIDE_OFFSETS[side]
    return dr, dc, 2 * opposite + (1 if h % 2 == 0 else 0)


def make_cell(
    card_type: str, rot: int, *, placed_by: str | None = None, move: int = 0
) -> dict[str, Any]:
    return {
        "type": card_type,
        "rot": rot % 4,
        "owners": [None] * len(CARD_TYPES[card_type]["areas"]),
        "placed_by": placed_by,
        "claimed": None,
        "move": move,
    }


def bounding_area(cells: Cells) -> int:
    if not cells:
        return 0
    coords = [parse_key(k) for k in cells]
    rows = [r for r, _ in coords]
    cols = [c for _, c in coords]
    return (max(rows) - min(rows) + 1) * (max(cols) - min(cols) + 1)


# --------------------------------------------------------------------------- regions


@dataclass
class Region:
    areas: list[AreaRef] = field(default_factory=list)
    cards: set[str] = field(default_factory=set)
    enclosed: bool = True
    # owner -> set of cards holding an area of that owner in this region
    owner_cards: dict[str, set[str]] = field(default_factory=dict)

    @property
    def color(self) -> str | None:
        if not self.owner_cards:
            return None
        if len(self.owner_cards) == 1:
            return next(iter(self.owner_cards))
        return GRAY

    def units(self) -> dict[str, int]:
        return {pid: len(cards) for pid, cards in self.owner_cards.items()}


@dataclass
class RegionMap:
    regions: list[Region]
    area_region: dict[AreaRef, int]

    def region_of(self, ref: AreaRef) -> Region:
        return self.regions[self.area_region[ref]]


def compute_regions(cells: Cells) -> RegionMap:
    parent: dict[AreaRef, AreaRef] = {}

    def find(x: AreaRef) -> AreaRef:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    lookup: dict[str, list[int]] = {}
    for key, cell in cells.items():
        lookup[key] = half_to_area(cell["type"], int(cell["rot"]))
        for idx in range(len(cell["owners"])):
            parent[(key, idx)] = (key, idx)

    open_areas: set[AreaRef] = set()
    for key, halves in lookup.items():
        r, c = parse_key(key)
        for h in range(8):
            dr, dc, nh = neighbor_half(h)
            nkey = cell_key(r + dr, c + dc)
            if nkey not in lookup:
                open_areas.add((key, halves[h]))
                continue
            a, b = find((key, halves[h])), find((nkey, lookup[nkey][nh]))
            if a != b:
                parent[a] = b

    roots: dict[AreaRef, int] = {}
    regions: list[Region] = []
    area_region: dict[AreaRef, int] = {}
    for ref in parent:
        root = find(ref)
        if root not in roots:
            roots[root] = len(regions)
            regions.append(Region())
        rid = roots[root]
        region = regions[rid]
        area_region[ref] = rid
        region.areas.append(ref)
        region.cards.add(ref[0])
        if ref in open_areas:
            region.enclosed = False
        owner = cells[ref[0]]["owners"][ref[1]]
        if owner is not None:
            region.owner_cards.setdefault(owner, set()).add(ref[0])
    return RegionMap(regions=regions, area_region=area_region)


# --------------------------------------------------------------------------- placement


def fits(cells: Cells, row: int, col: int, card_type: str, rot: int) -> bool:
    """Empty spot next to the board where every touching side matches line / no line."""
    if cell_key(row, col) in cells:
        return False
    lines = card_lines(card_type, rot)
    has_neighbor = False
    for side, (dr, dc) in enumerate(SIDE_OFFSETS):
        neighbor = cells.get(cell_key(row + dr, col + dc))
        if neighbor is None:
            continue
        has_neighbor = True
        neighbor_has_line = (side + 2) % 4 in card_lines(neighbor["type"], int(neighbor["rot"]))
        if (side in lines) != neighbor_has_line:
            return False
    return has_neighbor


def frontier(cells: Cells) -> set[tuple[int, int]]:
    spots: set[tuple[int, int]] = set()
    for key in cells:
        r, c = parse_key(key)
        for dr, dc in SIDE_OFFSETS:
            if cell_key(r + dr, c + dc) not in cells:
                spots.add((r + dr, c + dc))
    return spots


def legal_spots(cells: Cells, card_type: str) -> list[tuple[int, int, int]]:
    return sorted(
        (r, c, rot)
        for r, c in frontier(cells)
        for rot in range(4)
        if fits(cells, r, c, card_type, rot)
    )


def touching_regions(
    cells: Cells, regions: RegionMap, row: int, col: int, card_type: str, rot: int, area: int
) -> list[Region]:
    """Existing regions the given area of a card placed at (row, col) would join."""
    out: list[Region] = []
    for h in card_areas(card_type, rot)[area]:
        dr, dc, nh = neighbor_half(h)
        nkey = cell_key(row + dr, col + dc)
        neighbor = cells.get(nkey)
        if neighbor is None:
            continue
        n_area = half_to_area(neighbor["type"], int(neighbor["rot"]))[nh]
        out.append(regions.region_of((nkey, n_area)))
    return out


def claim_allowed(
    cells: Cells,
    regions: RegionMap,
    row: int,
    col: int,
    card_type: str,
    rot: int,
    area: int,
    player_id: str,
) -> bool:
    """A new area may only be claimed when the move does not grow one of the player's own
    areas (no area of the card touches a region holding any of their cards), and the claimed
    area may not touch an area of another player (white and gray are fine)."""
    if grows_own_area(cells, regions, row, col, card_type, rot, player_id):
        return False
    return all(
        region.color in (None, GRAY)
        for region in touching_regions(cells, regions, row, col, card_type, rot, area)
    )


def grows_own_area(
    cells: Cells, regions: RegionMap, row: int, col: int, card_type: str, rot: int, player_id: str
) -> bool:
    """True when placing the card (unclaimed) would join one of the player's regions."""
    return any(
        player_id in region.owner_cards
        for area in range(len(CARD_TYPES[card_type]["areas"]))
        for region in touching_regions(cells, regions, row, col, card_type, rot, area)
    )


@dataclass
class Placement:
    cells: Cells
    area_before: int
    area_after: int
    takeovers: list[dict[str, Any]]

    @property
    def penalty(self) -> int:
        return max(0, self.area_after - self.area_before)


def place_card(
    cells: Cells,
    row: int,
    col: int,
    card_type: str,
    rot: int,
    claim: int | None,
    player_id: str,
    move: int = 0,
) -> Placement | str:
    """Place a card and resolve colours. Returns the new cells or a rejection reason."""
    if card_type not in CARD_TYPES:
        return "unknown_card"
    rot %= 4
    if not fits(cells, row, col, card_type, rot):
        return "does_not_fit"
    n_areas = len(CARD_TYPES[card_type]["areas"])
    if claim is not None and not 0 <= claim < n_areas:
        return "invalid_area"
    before = compute_regions(cells)
    if claim is not None and not claim_allowed(
        cells, before, row, col, card_type, rot, claim, player_id
    ):
        return "claim_not_allowed"

    key = cell_key(row, col)
    new_cells: Cells = {k: {**v, "owners": list(v["owners"])} for k, v in cells.items()}
    cell = make_cell(card_type, rot, placed_by=player_id, move=move)
    if claim is not None:
        cell["owners"][claim] = player_id
        cell["claimed"] = claim
    new_cells[key] = cell

    after = compute_regions(new_cells)
    takeovers: list[dict[str, Any]] = []
    for rid in sorted({after.area_region[(key, idx)] for idx in range(n_areas)}):
        region = after.regions[rid]
        units = region.units()
        if not units:
            continue
        prior_gray = any(
            before.region_of(ref).color == GRAY for ref in region.areas if ref[0] != key
        )
        ranked = sorted(units.items(), key=lambda kv: kv[1], reverse=True)
        winner: str | None = ranked[0][0]
        if len(ranked) > 1:
            lead = ranked[0][1] - ranked[1][1]
            if lead < (2 if prior_gray else 1):
                winner = None
            else:
                takeovers.append({"winner": ranked[0][0], "losers": [pid for pid, _ in ranked[1:]]})
        if winner is not None:
            for ref_key, idx in region.areas:
                new_cells[ref_key]["owners"][idx] = winner

    return Placement(
        cells=new_cells,
        area_before=bounding_area(cells),
        area_after=bounding_area(new_cells),
        takeovers=takeovers,
    )


# --------------------------------------------------------------------------- scoring


def territory_scores(cells: Cells) -> dict[str, int]:
    """One point per card of a single-colour region; regions of one card score nothing and
    regions fully enclosed by lines score double."""
    scores: dict[str, int] = {}
    for region in compute_regions(cells).regions:
        color = region.color
        if color is None or color == GRAY or len(region.cards) < 2:
            continue
        points = len(region.cards) * (2 if region.enclosed else 1)
        scores[color] = scores.get(color, 0) + points
    return scores
