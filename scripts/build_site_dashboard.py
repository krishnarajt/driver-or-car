"""Build the JSON payload used by the static "Driver or Car" dashboard.

This goes well beyond season standings. The whole point of the dashboard is to
answer one question: *when a team does well, is it the car or the driver?*

The strongest evidence in public F1 data is the **teammate comparison**. Two
drivers in the same constructor drive effectively identical machinery in the
same races. If results were purely a function of the car, teammates would
always finish next to each other (P1-P2, P5-P6, ...). They very rarely do. The
gap that opens up between two drivers in the same car is the cleanest signal we
have for "the driver" — and strategy, reliability and racecraft fill in the
rest.

So this builder computes, on top of the existing standings/pace payload:

* teammate head-to-head (qualifying, race, points, wins, podiums, DNFs) for
  every constructor that fielded two regular drivers,
* the season-wide distribution of teammate finishing-position gaps (the "cars
  don't finish together" headline),
* strategy / luck proxies (positions gained from the grid, constructor
  reliability, pit-stop counts),
* a transparent per-season Driver-vs-Car verdict heuristic,
* a curated list of the most lopsided "same car, different result" duels of
  all time.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
F1DB = ROOT / "data" / "f1db" / "csv"
TRACING = ROOT / "data" / "tracinginsights"
ANALYSIS = ROOT / "analysis"
# Vite serves everything under site/public at the web root, so the generated
# dashboard data lives there and is picked up by both `npm run dev` and builds.
OUT = ROOT / "site" / "public" / "data"

# Era used for the headline "cars don't finish together" distribution. The
# modern era has two-car teams and reliable cars, which is the fairest test of
# the "if it were the car they'd finish together" claim.
HEADLINE_ERA_START = 2014


def read_f1db(filename: str, **kwargs: Any) -> pd.DataFrame:
    kwargs.setdefault("low_memory", False)
    return pd.read_csv(F1DB / filename, **kwargs)


def read_analysis(filename: str, **kwargs: Any) -> pd.DataFrame:
    kwargs.setdefault("low_memory", False)
    return pd.read_csv(ANALYSIS / filename, **kwargs)


def clean_value(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return clean_value(value)


def as_bool(value: Any) -> bool:
    return str(value).lower() == "true"


def points_label(value: Any) -> str:
    value = clean_value(value)
    if value is None:
        return "0"
    if isinstance(value, (int, float)) and float(value).is_integer():
        return f"{int(value):,}"
    return f"{float(value):,.1f}"


def round_or_none(value: Any, digits: int = 1) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return round(float(value), digits)


def flag_from_alpha2(alpha2: Any) -> str | None:
    if not isinstance(alpha2, str) or len(alpha2) != 2:
        return None
    alpha2 = alpha2.upper()
    if not alpha2.isalpha():
        return None
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in alpha2)


# --------------------------------------------------------------------------- #
# Standings (carried over from the original builder)
# --------------------------------------------------------------------------- #
def standings_records(
    frame: pd.DataFrame,
    id_column: str,
    name_map: pd.Series,
    extra_maps: dict[str, pd.Series] | None = None,
) -> list[dict[str, Any]]:
    extra_maps = extra_maps or {}
    records: list[dict[str, Any]] = []

    for row in frame.sort_values(["positionDisplayOrder", "positionNumber"]).to_dict("records"):
        entrant_id = row[id_column]
        record = {
            "rank": clean_value(row.get("positionNumber")),
            "positionText": clean_value(row.get("positionText")),
            "id": clean_value(entrant_id),
            "name": clean_value(name_map.get(entrant_id, entrant_id)),
            "points": clean_value(row.get("points")),
            "pointsLabel": points_label(row.get("points")),
            "championshipWon": as_bool(row.get("championshipWon")),
        }
        for output_key, mapping in extra_maps.items():
            source_key = f"{output_key}Id"
            mapped_id = row.get(source_key)
            record[output_key] = clean_value(mapping.get(mapped_id, mapped_id))
        records.append(record)

    return records


def leader_or_champion(records: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not records:
        return None
    champion = next((record for record in records if record["championshipWon"]), None)
    return champion or records[0]


def count_rows(path: Path) -> int:
    with path.open("rb") as handle:
        return max(sum(1 for _ in handle) - 1, 0)


def match_stats(summary: pd.DataFrame, column: str) -> dict[str, Any]:
    valid = summary[column].dropna()
    matches = int(valid.astype(bool).sum()) if not valid.empty else 0
    total = int(valid.count())
    rate = (matches / total * 100) if total else None
    return {
        "matches": matches,
        "total": total,
        "rate": round(rate, 1) if rate is not None else None,
    }


def pace_payload(row: pd.Series | None) -> dict[str, Any]:
    if row is None:
        return {}

    return {
        "qualifying": {
            "constructor": clean_value(row.get("qualifying_fastest_constructor")),
            "fastestRaces": clean_value(row.get("qualifying_fastest_races")),
            "racesAvailable": clean_value(row.get("qualifying_races_available")),
            "matchesConstructorChampion": clean_value(
                row.get("qualifying_fastest_is_constructor_champion")
            ),
        },
        "fastestLap": {
            "constructor": clean_value(row.get("fastest_lap_fastest_constructor")),
            "fastestRaces": clean_value(row.get("fastest_lap_fastest_races")),
            "racesAvailable": clean_value(row.get("fastest_lap_races_available")),
            "matchesConstructorChampion": clean_value(
                row.get("fastest_lap_fastest_is_constructor_champion")
            ),
        },
        "raceWins": {
            "constructor": clean_value(row.get("race_win_leader_constructor")),
            "wins": clean_value(row.get("race_wins")),
            "racesAvailable": clean_value(row.get("races_with_winner")),
            "matchesConstructorChampion": clean_value(row.get("race_win_leader_is_constructor_champion")),
        },
    }


# --------------------------------------------------------------------------- #
# Teammate / strategy analysis (the core of the "driver or car" argument)
# --------------------------------------------------------------------------- #
# A retirement is attributed to the *car* only when its recorded cause is a
# mechanical/technical failure — not a crash, collision, spin or off, which are
# racing incidents (driver/luck). Anything else (disqualification, withdrawal,
# illegal car, injury) is neither, and is excluded from the reliability metric.
INCIDENT_WORDS = ("collision", "accident", "spun", "spin", "crash", "contact",
                  "damage", "puncture", "debris", "off")
NON_CAR_WORDS = ("disqualif", "withdr", "illegal", "underweight", "injur",
                 "unwell", "ill", "did not", "excluded", "safety", "fatigue")


def classify_retirement(reason: Any) -> str:
    """Return 'mechanical' (the car), 'incident' (driver/racing), or 'other'."""
    if reason is None or (isinstance(reason, float) and pd.isna(reason)):
        return "other"
    text = str(reason).lower()
    if any(word in text for word in INCIDENT_WORDS):
        return "incident"
    if any(word in text for word in NON_CAR_WORDS):
        return "other"
    return "mechanical"


def prepare_results(race_results: pd.DataFrame) -> pd.DataFrame:
    rr = race_results.copy()
    rr["pos"] = pd.to_numeric(rr["positionNumber"], errors="coerce")
    rr["points"] = pd.to_numeric(rr["points"], errors="coerce").fillna(0.0)

    # Add sprint-race points so per-driver season totals match the official
    # standings (the main race-results file holds Grand Prix points only). This
    # only affects point sums; finishing positions/wins stay Grand-Prix-based.
    sprint_path = F1DB / "f1db-races-sprint-race-results.csv"
    if sprint_path.exists():
        sprint = pd.read_csv(sprint_path, low_memory=False)
        sprint["points"] = pd.to_numeric(sprint["points"], errors="coerce").fillna(0.0)
        sp = (
            sprint.groupby(["raceId", "driverId"], as_index=False)["points"]
            .sum()
            .rename(columns={"points": "sprintPoints"})
        )
        rr = rr.merge(sp, on=["raceId", "driverId"], how="left")
        rr["sprintPoints"] = rr["sprintPoints"].fillna(0.0)
        rr["points"] = rr["points"] + rr["sprintPoints"]

    rr["qpos"] = pd.to_numeric(rr["qualificationPositionNumber"], errors="coerce")
    rr["gpos"] = pd.to_numeric(rr["gridPositionNumber"], errors="coerce")
    # Fall back to grid position when an explicit qualifying classification is
    # missing (older seasons / pre-qualifying formats).
    rr["qpos"] = rr["qpos"].fillna(rr["gpos"])
    rr["gained"] = pd.to_numeric(rr["positionsGained"], errors="coerce")
    rr["pits"] = pd.to_numeric(rr["pitStops"], errors="coerce")
    rr["pole"] = rr["polePosition"].astype(str).str.lower().eq("true")
    rr["finished"] = rr["pos"].notna()
    # Did the driver actually take the start? Excludes DNS/DNQ/DNPQ rows so the
    # teammate "shared races" count means races both drivers raced.
    rr["started"] = rr["finished"] | ~rr["positionText"].astype(str).str.upper().isin(
        ["DNS", "DNQ", "DNPQ", "DNP", "EX"]
    )
    rr["retirement"] = rr["reasonRetired"].map(classify_retirement)
    return rr


def gap_buckets(gaps: list[int]) -> list[dict[str, Any]]:
    labels = [
        (1, 1, "Adjacent (P1–P2, P5–P6…)"),
        (2, 2, "2 places apart"),
        (3, 4, "3–4 places apart"),
        (5, 9, "5–9 places apart"),
        (10, 10_000, "10+ places apart"),
    ]
    total = len(gaps) or 1
    out = []
    for lo, hi, label in labels:
        count = sum(1 for g in gaps if lo <= g <= hi)
        out.append(
            {
                "label": label,
                "count": count,
                "pct": round(count / total * 100, 1),
            }
        )
    return out


def teammate_finish_gaps(rr: pd.DataFrame) -> list[int]:
    """|posA - posB| for every constructor that had exactly two classified
    finishers in a race. This is the raw "do the two cars finish together?"
    evidence."""
    gaps: list[int] = []
    finishers = rr[rr["finished"]]
    for _, sub in finishers.groupby(["raceId", "constructorId"]):
        if sub["driverId"].nunique() == 2 and len(sub) == 2:
            positions = sorted(sub["pos"].tolist())
            gaps.append(int(positions[1] - positions[0]))
    return gaps


def driver_meta_maps(drivers: pd.DataFrame, countries: pd.DataFrame) -> dict[str, dict[str, Any]]:
    alpha2 = countries.set_index("id")["alpha2Code"]
    meta: dict[str, dict[str, Any]] = {}
    for row in drivers.to_dict("records"):
        country = alpha2.get(row.get("nationalityCountryId"))
        meta[row["id"]] = {
            "name": row.get("name"),
            "abbr": (row.get("abbreviation") or (row.get("name") or "")[:3]).upper(),
            "country": (country or "").upper() or None,
            "flag": flag_from_alpha2(country),
        }
    return meta


def build_pair(
    sub: pd.DataFrame,
    driver_meta: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    """Given all race-result rows for one constructor in one season, compute a
    head-to-head between its two main drivers."""
    # Pick the pair by championship points (entries as tiebreaker), NOT raw race
    # count — otherwise a low-scoring driver who happened to start more races can
    # displace the genuine number-two (e.g. Peterson behind a pay-driver in 1978).
    ranked = (
        sub.groupby("driverId")
        .agg(pts=("points", "sum"), entries=("raceId", "nunique"))
        .sort_values(["pts", "entries"], ascending=[False, False])
    )
    if len(ranked) < 2:
        return None
    a_id, b_id = ranked.index[0], ranked.index[1]

    def driver_block(did: str) -> dict[str, Any]:
        d = sub[sub["driverId"].eq(did)]
        info = driver_meta.get(did, {"name": did, "abbr": did[:3].upper(), "country": None, "flag": None})
        return {
            "id": did,
            "name": info["name"],
            "abbr": info["abbr"],
            "country": info["country"],
            "flag": info["flag"],
            "points": round_or_none(d["points"].sum(), 1),
            "wins": int((d["pos"] == 1).sum()),
            "podiums": int((d["pos"] <= 3).sum()),
            "poles": int(d["pole"].sum()),
            "entries": int(d["raceId"].nunique()),
            "dnfs": int((~d["finished"]).sum()),
            "bestFinish": clean_value(d["pos"].min()),
        }

    a = driver_block(a_id)
    b = driver_block(b_id)

    # Head-to-head only on races where BOTH started — same car, same race.
    # Collapse the rare duplicate rows (shared cars, restarts) to the primary
    # classification so each driver has one row per race, and drop DNS/DNQ rows
    # so a driver who never took the start can't score a "qualifying win".
    def one_row_per_race(did: str) -> pd.DataFrame:
        rows = sub[sub["driverId"].eq(did) & sub["started"]]
        return (
            rows.sort_values("positionDisplayOrder")
            .drop_duplicates("raceId")
            .set_index("raceId")
        )

    a_rows = one_row_per_race(a_id)
    b_rows = one_row_per_race(b_id)
    shared = a_rows.index.intersection(b_rows.index)

    quali_a = quali_b = race_a = race_b = 0
    quali_shared = race_shared = 0
    finish_gaps: list[int] = []
    # Ordered by round so the front-end can draw the two drivers' race-by-race
    # finishing positions and literally watch the same car diverge.
    shared_sorted = sorted(shared, key=lambda r: a_rows.at[r, "round"])
    timeline: list[dict[str, Any]] = []
    for rid in shared_sorted:
        qa, qb = a_rows.at[rid, "qpos"], b_rows.at[rid, "qpos"]
        if pd.notna(qa) and pd.notna(qb) and qa != qb:
            quali_shared += 1
            if qa < qb:
                quali_a += 1
            else:
                quali_b += 1
        pa, pb = a_rows.at[rid, "pos"], b_rows.at[rid, "pos"]
        if pd.notna(pa) and pd.notna(pb):
            race_shared += 1
            finish_gaps.append(int(abs(pa - pb)))
            if pa < pb:
                race_a += 1
            elif pb < pa:
                race_b += 1
        timeline.append(
            {
                "r": clean_value(a_rows.at[rid, "round"]),
                "fa": clean_value(pa),
                "fb": clean_value(pb),
            }
        )

    # Share is between *these two* drivers (the segments sum to 100); the real
    # team total (incl. any other drivers) is attached separately by callers.
    pair_points = (a["points"] or 0) + (b["points"] or 0)
    a_share = round((a["points"] or 0) / pair_points * 100, 1) if pair_points else None
    b_share = round((b["points"] or 0) / pair_points * 100, 1) if pair_points else None

    return {
        "a": a,
        "b": b,
        "sharedRaces": int(len(shared)),
        "qualiH2H": {"a": quali_a, "b": quali_b, "races": quali_shared},
        "raceH2H": {"a": race_a, "b": race_b, "races": race_shared},
        "pointsShare": {"a": a_share, "b": b_share},
        "pairPoints": round_or_none(pair_points, 1),
        "finishGapMean": round_or_none(
            sum(finish_gaps) / len(finish_gaps) if finish_gaps else None, 2
        ),
        "bothFinished": len(finish_gaps),
        "timeline": timeline,
    }


def season_teammates(
    rr_year: pd.DataFrame,
    constructor_names: pd.Series,
    engine_names: pd.Series,
    driver_meta: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for cid, sub in rr_year.groupby("constructorId"):
        pair = build_pair(sub, driver_meta)
        if not pair or pair["sharedRaces"] < 3:
            continue
        engine_id = sub["engineManufacturerId"].mode()
        engine_id = engine_id.iloc[0] if not engine_id.empty else None
        # Real constructor season total — includes any 3rd/4th drivers, so the
        # dropdown label is the team's actual points, not just the pair's.
        team_points = float(sub["points"].sum())
        driver_count = int(sub["driverId"].nunique())
        pair.update(
            {
                "constructorId": cid,
                "constructor": clean_value(constructor_names.get(cid, cid)),
                "engine": clean_value(engine_names.get(engine_id, engine_id)),
                "teamPoints": round_or_none(team_points, 1),
                "driverCount": driver_count,
            }
        )
        pairs.append(pair)
    pairs.sort(key=lambda p: p["teamPoints"] or 0, reverse=True)
    return pairs


def season_strategy(rr_year: pd.DataFrame, driver_meta: dict[str, dict[str, Any]],
                    constructor_names: pd.Series) -> dict[str, Any]:
    # Drivers who dragged the car forward from where it qualified.
    gained = (
        rr_year.dropna(subset=["gained"])
        .groupby("driverId")["gained"].sum()
        .sort_values(ascending=False)
    )
    top_movers = [
        {
            "driver": driver_meta.get(did, {}).get("name", did),
            "abbr": driver_meta.get(did, {}).get("abbr"),
            "flag": driver_meta.get(did, {}).get("flag"),
            "gained": int(val),
        }
        for did, val in gained.head(5).items()
        if val > 0
    ]

    # Constructor reliability: share of entries lost to a *mechanical* failure
    # (engine, gearbox, hydraulics…), NOT crashes — crashes are the driver, and
    # counting them here would overstate the car's role.
    reliability = []
    for cid, sub in rr_year.groupby("constructorId"):
        entries = int(len(sub))
        if entries < 4:
            continue
        dnf = sub[~sub["finished"]]
        mech = int((dnf["retirement"] == "mechanical").sum())
        incident = int((dnf["retirement"] == "incident").sum())
        reliability.append(
            {
                "constructor": clean_value(constructor_names.get(cid, cid)),
                "entries": entries,
                "mechanicalDnfs": mech,
                "incidentDnfs": incident,
                "dnfRate": round(mech / entries * 100, 1),
            }
        )
    reliability.sort(key=lambda r: r["dnfRate"])

    pit = rr_year.dropna(subset=["pits"])
    avg_pits = round(float(pit["pits"].mean()), 2) if not pit.empty else None

    return {
        "topMovers": top_movers,
        "mostReliable": reliability[:3],
        "leastReliable": list(reversed(reliability[-3:])) if len(reliability) >= 3 else [],
        "avgPitStops": avg_pits,
    }


def season_verdict(
    pairs: list[dict[str, Any]],
    finish_gaps: list[int],
    champion_share: Any,
    constructor_standings_records: list[dict[str, Any]],
    partial: bool = False,
) -> dict[str, Any]:
    """Two independent forces, deliberately NOT collapsed into one number.

    These are transparent heuristics, not causal truth — they are the *visible
    fingerprints* of car and driver, shown side by side.

    carForce   — how much the field was shaped by machinery: the top
                 constructor's share of all constructor points. A runaway car
                 means the grid order was largely set before lights out.
    driverForce — how much the driver mattered: how far apart teammates in
                 identical cars finished. If the car decided everything, every
                 team would lock out adjacent positions and this would be 0.

    Both can be high at once: a dominant car can still leave a big gap between
    its two drivers — which is exactly the "great car, but the driver still
    decided it" story.
    """
    car_force = None
    pts = [
        r["points"]
        for r in constructor_standings_records
        if isinstance(r.get("points"), (int, float))
    ]
    if pts and sum(pts) > 0:
        car_force = round(max(pts) / sum(pts) * 100)

    driver_force = None
    adjacency = None
    if finish_gaps:
        adjacency = sum(1 for g in finish_gaps if g <= 1) / len(finish_gaps)
        driver_force = round((1 - adjacency) * 100)

    champ_team_share = round_or_none(
        champion_share * 100 if champion_share is not None else None, 1
    )

    sample_size = len(finish_gaps)
    low_sample = sample_size > 0 and sample_size < 20

    label = None
    spotlight = None
    if car_force is not None and driver_force is not None:
        car_high = car_force >= 32  # one team owning ~a third of all points
        driver_high = driver_force >= 60
        if car_high and driver_high:
            label = "Fast car, driver decided it"
            spotlight = (
                "One car dominated the grid — yet its two drivers still finished "
                "worlds apart. The machinery set the stage; the driver decided the ending."
            )
        elif car_high and not driver_high:
            label = "The car did the talking"
            spotlight = (
                "A dominant car carried the whole team, and its two drivers "
                "finished close together — most of the result came from the machinery."
            )
        elif driver_high:
            label = "Driver-defined season"
            spotlight = (
                "No single car ran away with it, and teammates in identical "
                "machinery finished far apart. This one leaned on who was driving."
            )
        else:
            label = "A genuine mix"
            spotlight = (
                "Neither force dominates: competitive cars and moderately spread "
                "teammates. Car and driver shared the credit."
            )
    elif driver_force is not None:
        # Pre-1958: no constructors' championship, so there is no car-force
        # reading. Still report the driver-spread signal on its own terms.
        if driver_force >= 60:
            label = "Driver-spread season"
            spotlight = (
                "Before 1958 there was no constructors' title, so there is no "
                "car-force reading — but teammates in the same machinery still "
                "finished far apart."
            )
        else:
            label = "Closely matched teammates"
            spotlight = (
                "No constructors' championship existed yet, so there is no "
                "car-force reading — and teammates here finished fairly close together."
            )

    return {
        "carForce": car_force,
        "driverForce": driver_force,
        "championTeamShare": champ_team_share,
        "teammateAdjacencyRate": round_or_none(
            adjacency * 100 if adjacency is not None else None, 1
        ),
        "sampleSize": sample_size,
        "lowSample": low_sample,
        "partial": bool(partial),
        "label": label,
        "spotlight": spotlight,
    }


def flagship_duels(
    rr: pd.DataFrame,
    constructor_names: pd.Series,
    engine_names: pd.Series,
    driver_meta: dict[str, dict[str, Any]],
    limit: int = 10,
) -> list[dict[str, Any]]:
    """Most lopsided 'same car, different driver result' seasons of all time."""
    candidates: list[dict[str, Any]] = []
    for (year, cid), sub in rr.groupby(["year", "constructorId"]):
        pair = build_pair(sub, driver_meta)
        if not pair:
            continue
        pa, pb = pair["a"], pair["b"]
        pair_points = pair["pairPoints"] or 0
        # Require a genuine same-season, same-races comparison: both drivers ran
        # most of the year and were classified together often enough that the
        # gap reflects pace, not one driver being a part-season stand-in.
        both_classified = pair["raceH2H"]["races"]
        entry_balance = (
            min(pa["entries"], pb["entries"]) / max(pa["entries"], pb["entries"])
            if max(pa["entries"], pb["entries"])
            else 0
        )
        if (
            pair["sharedRaces"] < 8
            or both_classified < 6
            or entry_balance < 0.6
            or pair_points < 40
        ):
            continue
        pmax = max(pa["points"] or 0, pb["points"] or 0)
        pmin = min(pa["points"] or 0, pb["points"] or 0)
        # Lopsidedness of the *two drivers* (independent of any 3rd driver).
        imbalance = (pmax - pmin) / (pmax + pmin) if (pmax + pmin) else 0
        # interestingness: lopsided AND title-relevant (lots of points)
        score = imbalance * (pair_points ** 0.5)
        engine_id = sub["engineManufacturerId"].mode()
        engine_id = engine_id.iloc[0] if not engine_id.empty else None
        candidates.append(
            {
                "year": int(year),
                "constructorId": cid,
                "constructor": clean_value(constructor_names.get(cid, cid)),
                "engine": clean_value(engine_names.get(engine_id, engine_id)),
                "teamPoints": round_or_none(float(sub["points"].sum()), 1),
                "imbalance": round(imbalance * 100, 1),
                "score": score,
                "a": pa,
                "b": pb,
                "qualiH2H": pair["qualiH2H"],
                "raceH2H": pair["raceH2H"],
                "pointsShare": pair["pointsShare"],
                "sharedRaces": pair["sharedRaces"],
            }
        )
    candidates.sort(key=lambda c: c["score"], reverse=True)
    # Keep variety: at most two showcase seasons per constructor so the list
    # isn't dominated by a single dynasty.
    per_constructor: dict[str, int] = defaultdict(int)
    chosen: list[dict[str, Any]] = []
    for c in candidates:
        if per_constructor[c["constructorId"]] >= 2:
            continue
        per_constructor[c["constructorId"]] += 1
        c.pop("score", None)
        chosen.append(c)
        if len(chosen) >= limit:
            break
    return chosen


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    seasons = read_f1db("f1db-seasons.csv")
    races = read_f1db("f1db-races.csv")
    race_results = read_f1db("f1db-races-race-results.csv")
    driver_standings = read_f1db("f1db-seasons-driver-standings.csv")
    constructor_standings = read_f1db("f1db-seasons-constructor-standings.csv")
    drivers = read_f1db("f1db-drivers.csv")
    constructors = read_f1db("f1db-constructors.csv")
    engines = read_f1db("f1db-engine-manufacturers.csv")
    countries = read_f1db("f1db-countries.csv")
    summary = read_analysis("yearly_fastest_car_summary.csv")

    driver_names = drivers.set_index("id")["name"]
    constructor_names = constructors.set_index("id")["name"]
    engine_names = engines.set_index("id")["name"]
    summary_by_year = {int(row["year"]): row for _, row in summary.iterrows()}
    driver_meta = driver_meta_maps(drivers, countries)

    rr = prepare_results(race_results)
    champ_share_by_year = {
        int(row["year"]): row.get("driver_champion_primary_constructor_points_share")
        for _, row in summary.iterrows()
    }

    race_counts = races.groupby("year")["id"].nunique()
    completed_race_counts = rr.groupby("year")["raceId"].nunique()
    result_entry_counts = rr.groupby("year")["raceId"].count()
    rr_by_year = {year: frame for year, frame in rr.groupby("year")}

    season_payloads = []
    for year in sorted(seasons["year"].dropna().astype(int).unique()):
        driver_frame = driver_standings[driver_standings["year"].eq(year)]
        constructor_frame = constructor_standings[constructor_standings["year"].eq(year)]

        driver_records = standings_records(driver_frame, "driverId", driver_names)
        constructor_records = standings_records(
            constructor_frame,
            "constructorId",
            constructor_names,
            {"engineManufacturer": engine_names},
        )
        driver_title = leader_or_champion(driver_records)
        constructor_title = leader_or_champion(constructor_records)
        driver_title_decided = bool(driver_title and driver_title["championshipWon"])
        constructor_title_decided = bool(
            constructor_title and constructor_title["championshipWon"]
        )
        scheduled = int(race_counts.get(year, 0))
        completed = int(completed_race_counts.get(year, 0))
        is_partial = scheduled > completed or not driver_title_decided

        rr_year = rr_by_year.get(year)
        if rr_year is not None and not rr_year.empty:
            pairs = season_teammates(rr_year, constructor_names, engine_names, driver_meta)
            finish_gaps = teammate_finish_gaps(rr_year)
            strategy = season_strategy(rr_year, driver_meta, constructor_names)
        else:
            pairs, finish_gaps, strategy = [], [], {}

        biggest_gap_pair = None
        if pairs:
            ranked = sorted(
                (p for p in pairs if p["pointsShare"]["a"] is not None),
                key=lambda p: abs((p["pointsShare"]["a"] or 0) - (p["pointsShare"]["b"] or 0)),
                reverse=True,
            )
            if ranked:
                top = ranked[0]
                biggest_gap_pair = {
                    "constructor": top["constructor"],
                    "a": {"abbr": top["a"]["abbr"], "points": top["a"]["points"]},
                    "b": {"abbr": top["b"]["abbr"], "points": top["b"]["points"]},
                }

        verdict = season_verdict(
            pairs,
            finish_gaps,
            champ_share_by_year.get(year),
            constructor_records,
            partial=is_partial,
        )

        teammate_summary = {
            "pairCount": len(pairs),
            "adjacencyRate": round(
                sum(1 for g in finish_gaps if g <= 1) / len(finish_gaps) * 100, 1
            )
            if finish_gaps
            else None,
            "medianFinishGap": clean_value(pd.Series(finish_gaps).median()) if finish_gaps else None,
            "sampleSize": len(finish_gaps),
            "gapBuckets": gap_buckets(finish_gaps) if finish_gaps else [],
            "biggestGapPair": biggest_gap_pair,
        }

        season_payloads.append(
            {
                "year": year,
                "status": "complete" if not is_partial else "partial",
                "racesScheduled": scheduled,
                "racesWithResults": completed,
                "resultEntries": int(result_entry_counts.get(year, 0)),
                "driverTitleDecided": driver_title_decided,
                "constructorTitleDecided": constructor_title_decided,
                "driverTitle": driver_title,
                "constructorTitle": constructor_title,
                "driverStandings": driver_records,
                "constructorStandings": constructor_records,
                "pace": pace_payload(summary_by_year.get(year)),
                "teammates": pairs,
                "teammateSummary": teammate_summary,
                "strategy": strategy,
                "verdict": verdict,
            }
        )

    latest_year = max(season["year"] for season in season_payloads)
    latest_completed_years = [
        season["year"] for season in season_payloads if season["driverTitleDecided"]
    ]
    latest_completed_year = max(latest_completed_years) if latest_completed_years else None
    latest_season = next(season for season in season_payloads if season["year"] == latest_year)

    # Headline distribution across the modern era — capped at the last COMPLETED
    # season so an in-progress year isn't folded into a "settled" claim.
    headline_end = latest_completed_year or latest_year
    headline_gaps = teammate_finish_gaps(
        rr[(rr["year"] >= HEADLINE_ERA_START) & (rr["year"] <= headline_end)]
    )
    headline_n = len(headline_gaps)
    adjacency_rate = (
        round(sum(1 for g in headline_gaps if g <= 1) / headline_n * 100, 1)
        if headline_n
        else None
    )

    duels = flagship_duels(rr, constructor_names, engine_names, driver_meta)

    payload = {
        "meta": {
            "source": "Local F1DB and TracingInsights CSV exports",
            "seasonStart": int(min(seasons["year"])),
            "seasonEnd": latest_year,
            "latestCompletedSeason": latest_completed_year,
            "generatedFrom": [
                "data/f1db/csv/f1db-races-race-results.csv",
                "data/f1db/csv/f1db-seasons-driver-standings.csv",
                "data/f1db/csv/f1db-seasons-constructor-standings.csv",
                "analysis/yearly_fastest_car_summary.csv",
            ],
        },
        "headline": {
            "era": f"{HEADLINE_ERA_START}–{headline_end}",
            "sampleSize": headline_n,
            "adjacencyRate": adjacency_rate,
            "meanGap": round(sum(headline_gaps) / headline_n, 2) if headline_n else None,
            "gap5PlusRate": round(
                sum(1 for g in headline_gaps if g >= 5) / headline_n * 100, 1
            )
            if headline_n
            else None,
            "gapBuckets": gap_buckets(headline_gaps),
        },
        "overview": {
            "seasons": len(season_payloads),
            "driverChampionshipSeasons": sum(
                1 for season in season_payloads if season["driverTitleDecided"]
            ),
            "constructorChampionshipSeasons": sum(
                1 for season in season_payloads if season["constructorTitleDecided"]
            ),
            "races": int(races["id"].nunique()),
            "raceResultRows": count_rows(F1DB / "f1db-races-race-results.csv"),
            "qualifyingRows": count_rows(F1DB / "f1db-races-qualifying-results.csv"),
            "lapTimeRows": count_rows(TRACING / "lap_times.csv"),
            "latestYear": latest_year,
            "latestRacesWithResults": latest_season["racesWithResults"],
            "latestRacesScheduled": latest_season["racesScheduled"],
        },
        "matchStats": {
            "driverConstructorTitleDouble": match_stats(
                summary, "driver_champion_primary_constructor_won_constructors_title"
            ),
            "qualifyingLeaderConstructorChampion": match_stats(
                summary, "qualifying_fastest_is_constructor_champion"
            ),
            "fastestLapLeaderConstructorChampion": match_stats(
                summary, "fastest_lap_fastest_is_constructor_champion"
            ),
            "raceWinLeaderConstructorChampion": match_stats(
                summary, "race_win_leader_is_constructor_champion"
            ),
        },
        "flagshipDuels": duels,
        "seasons": season_payloads,
    }

    output_path = OUT / "season-dashboard.json"
    output_path.write_text(
        json.dumps(json_ready(payload), indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {output_path.relative_to(ROOT)}")
    print(
        f"Headline ({payload['headline']['era']}): teammates finish adjacent "
        f"only {adjacency_rate}% of the time (n={headline_n})."
    )


if __name__ == "__main__":
    main()
