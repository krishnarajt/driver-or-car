"""Build starter F1 speed-vs-title analysis tables.

The public data cannot directly isolate "car speed" from driver, fuel,
tyres, setup, traffic, weather, and strategy. This script creates transparent
proxies:

1. Fastest constructor by qualifying pace: most race weekends where a
   constructor had the fastest available qualifying lap. Older formats use
   timeMillis; knockout formats use the best available Q1/Q2/Q3 time.
2. Fastest constructor by race fastest lap: most races where a constructor
   owned the quickest race lap.
3. Race-win leader: most race wins by constructor.

Outputs land in ../analysis.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
F1DB = ROOT / "data" / "f1db" / "csv"
TRACING = ROOT / "data" / "tracinginsights"
OUT = ROOT / "analysis"


def read_f1db(filename: str, **kwargs) -> pd.DataFrame:
    kwargs.setdefault("low_memory", False)
    return pd.read_csv(F1DB / filename, **kwargs)


def read_tracing(filename: str, **kwargs) -> pd.DataFrame:
    kwargs.setdefault("low_memory", False)
    return pd.read_csv(TRACING / filename, **kwargs)


def true_mask(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().eq("true")


def bool_compare(df: pd.DataFrame, left: str, right: str) -> pd.Series:
    both_present = df[left].notna() & df[right].notna()
    result = pd.Series(pd.NA, index=df.index, dtype="boolean")
    result.loc[both_present] = df.loc[both_present, left].eq(df.loc[both_present, right])
    return result


def season_speed_leaders(
    timing: pd.DataFrame,
    time_col: str,
    prefix: str,
) -> pd.DataFrame:
    """Find the season leader using race-level fastest constructor counts."""
    needed = ["year", "raceId", "constructorId", time_col]
    data = timing[needed].copy()
    data[time_col] = pd.to_numeric(data[time_col], errors="coerce")
    data = data.dropna(subset=["year", "raceId", "constructorId", time_col])

    best_col = f"{prefix}_best_millis"
    race_best_col = f"{prefix}_race_best_millis"
    gap_col = f"{prefix}_avg_gap_pct"
    count_col = f"{prefix}_fastest_races"
    available_col = f"{prefix}_races_available"

    constructor_best = (
        data.groupby(["year", "raceId", "constructorId"], as_index=False)[time_col]
        .min()
        .rename(columns={time_col: best_col})
    )
    race_best = (
        constructor_best.groupby(["year", "raceId"], as_index=False)[best_col]
        .min()
        .rename(columns={best_col: race_best_col})
    )
    per_constructor_race = constructor_best.merge(race_best, on=["year", "raceId"], how="left")
    per_constructor_race[gap_col] = (
        per_constructor_race[best_col] / per_constructor_race[race_best_col] - 1
    ) * 100

    fastest_rows = per_constructor_race[
        per_constructor_race[best_col].eq(per_constructor_race[race_best_col])
    ]
    fastest_counts = (
        fastest_rows.groupby(["year", "constructorId"], as_index=False)["raceId"]
        .nunique()
        .rename(columns={"raceId": count_col})
    )
    season_pace = (
        per_constructor_race.groupby(["year", "constructorId"], as_index=False)
        .agg(
            **{
                gap_col: (gap_col, "mean"),
                f"{prefix}_constructor_races_entered": ("raceId", "nunique"),
            }
        )
        .merge(fastest_counts, on=["year", "constructorId"], how="left")
    )
    season_pace[count_col] = season_pace[count_col].fillna(0).astype(int)

    available = (
        per_constructor_race.groupby("year", as_index=False)["raceId"]
        .nunique()
        .rename(columns={"raceId": available_col})
    )
    season_pace = season_pace.merge(available, on="year", how="left")

    leaders = (
        season_pace.sort_values(
            ["year", count_col, gap_col, "constructorId"],
            ascending=[True, False, True, True],
        )
        .drop_duplicates("year")
        .rename(columns={"constructorId": f"{prefix}_fastest_constructor_id"})
    )
    return leaders


def race_win_leaders(race_results: pd.DataFrame) -> pd.DataFrame:
    data = race_results[["year", "raceId", "constructorId", "positionNumber"]].copy()
    data["positionNumber"] = pd.to_numeric(data["positionNumber"], errors="coerce")
    winners = data[data["positionNumber"].eq(1)].dropna(subset=["constructorId"])
    wins = (
        winners.groupby(["year", "constructorId"], as_index=False)["raceId"]
        .nunique()
        .rename(columns={"raceId": "race_wins"})
    )
    available = (
        winners.groupby("year", as_index=False)["raceId"]
        .nunique()
        .rename(columns={"raceId": "races_with_winner"})
    )
    leaders = (
        wins.merge(available, on="year", how="left")
        .sort_values(["year", "race_wins", "constructorId"], ascending=[True, False, True])
        .drop_duplicates("year")
        .rename(columns={"constructorId": "race_win_leader_constructor_id"})
    )
    return leaders


def main() -> None:
    OUT.mkdir(exist_ok=True)

    seasons = read_f1db("f1db-seasons.csv")[["year"]].drop_duplicates()
    races = read_f1db("f1db-races.csv")
    constructors = read_f1db("f1db-constructors.csv")
    drivers = read_f1db("f1db-drivers.csv")
    constructor_standings = read_f1db("f1db-seasons-constructor-standings.csv")
    driver_standings = read_f1db("f1db-seasons-driver-standings.csv")
    qualifying = read_f1db("f1db-races-qualifying-results.csv")
    fastest_laps = read_f1db("f1db-races-fastest-laps.csv")
    race_results = read_f1db("f1db-races-race-results.csv")

    constructor_names = constructors.set_index("id")["name"]
    driver_names = drivers.set_index("id")["fullName"]

    constructor_champs = (
        constructor_standings[true_mask(constructor_standings["championshipWon"])]
        [["year", "constructorId", "points"]]
        .rename(
            columns={
                "constructorId": "constructor_champion_id",
                "points": "constructor_champion_points",
            }
        )
    )
    constructor_champs["constructor_champion"] = constructor_champs[
        "constructor_champion_id"
    ].map(constructor_names)

    driver_champs = (
        driver_standings[true_mask(driver_standings["championshipWon"])]
        [["year", "driverId", "points"]]
        .rename(columns={"driverId": "driver_champion_id", "points": "driver_champion_points"})
    )
    driver_champs["driver_champion"] = driver_champs["driver_champion_id"].map(driver_names)

    rr = race_results.copy()
    rr["points"] = pd.to_numeric(rr["points"], errors="coerce").fillna(0)
    rr["positionNumber"] = pd.to_numeric(rr["positionNumber"], errors="coerce")
    rr["win"] = rr["positionNumber"].eq(1)

    driver_constructor_points = (
        rr.groupby(["year", "constructorId", "driverId"], as_index=False)
        .agg(
            driver_constructor_points=("points", "sum"),
            driver_constructor_race_wins=("win", "sum"),
            driver_constructor_result_entries=("raceId", "nunique"),
        )
        .sort_values(
            ["year", "constructorId", "driver_constructor_points", "driver_constructor_race_wins"],
            ascending=[True, True, False, False],
        )
    )
    constructor_result_points = (
        driver_constructor_points.groupby(["year", "constructorId"], as_index=False)[
            "driver_constructor_points"
        ]
        .sum()
        .rename(columns={"driver_constructor_points": "constructor_result_points"})
    )
    driver_constructor_points = driver_constructor_points.merge(
        constructor_result_points, on=["year", "constructorId"], how="left"
    )
    driver_constructor_points["driver_constructor_points_share"] = (
        driver_constructor_points["driver_constructor_points"]
        / driver_constructor_points["constructor_result_points"].where(
            driver_constructor_points["constructor_result_points"].ne(0)
        )
    )
    driver_constructor_points["constructor"] = driver_constructor_points["constructorId"].map(
        constructor_names
    )
    driver_constructor_points["driver"] = driver_constructor_points["driverId"].map(driver_names)
    driver_constructor_points[
        [
            "year",
            "constructorId",
            "constructor",
            "driverId",
            "driver",
            "driver_constructor_points",
            "constructor_result_points",
            "driver_constructor_points_share",
            "driver_constructor_race_wins",
            "driver_constructor_result_entries",
        ]
    ].to_csv(OUT / "driver_points_within_constructor.csv", index=False)

    champion_primary_constructor = (
        driver_constructor_points.merge(driver_champs[["year", "driver_champion_id"]], on="year")
        .query("driverId == driver_champion_id")
        .sort_values(
            ["year", "driver_constructor_points", "driver_constructor_race_wins"],
            ascending=[True, False, False],
        )
        .drop_duplicates("year")
        [
            [
                "year",
                "constructorId",
                "constructor",
                "driver_constructor_points_share",
            ]
        ]
        .rename(
            columns={
                "constructorId": "driver_champion_primary_constructor_id",
                "constructor": "driver_champion_primary_constructor",
                "driver_constructor_points_share": "driver_champion_primary_constructor_points_share",
            }
        )
    )

    qualifying_time_cols = ["timeMillis", "q1Millis", "q2Millis", "q3Millis"]
    qualifying["bestQualifyingMillis"] = (
        qualifying[qualifying_time_cols].apply(pd.to_numeric, errors="coerce").min(axis=1)
    )

    qualifying_leaders = season_speed_leaders(qualifying, "bestQualifyingMillis", "qualifying")
    fastest_lap_leaders = season_speed_leaders(fastest_laps, "timeMillis", "fastest_lap")
    race_win_leader = race_win_leaders(race_results)

    summary = (
        seasons.merge(constructor_champs, on="year", how="left")
        .merge(driver_champs, on="year", how="left")
        .merge(champion_primary_constructor, on="year", how="left")
        .merge(qualifying_leaders, on="year", how="left")
        .merge(fastest_lap_leaders, on="year", how="left")
        .merge(race_win_leader, on="year", how="left")
        .sort_values("year")
    )

    summary["qualifying_fastest_constructor"] = summary[
        "qualifying_fastest_constructor_id"
    ].map(constructor_names)
    summary["fastest_lap_fastest_constructor"] = summary[
        "fastest_lap_fastest_constructor_id"
    ].map(constructor_names)
    summary["race_win_leader_constructor"] = summary["race_win_leader_constructor_id"].map(
        constructor_names
    )

    summary["qualifying_fastest_is_constructor_champion"] = bool_compare(
        summary, "qualifying_fastest_constructor_id", "constructor_champion_id"
    )
    summary["fastest_lap_fastest_is_constructor_champion"] = bool_compare(
        summary, "fastest_lap_fastest_constructor_id", "constructor_champion_id"
    )
    summary["race_win_leader_is_constructor_champion"] = bool_compare(
        summary, "race_win_leader_constructor_id", "constructor_champion_id"
    )
    summary["driver_champion_primary_constructor_won_constructors_title"] = bool_compare(
        summary, "driver_champion_primary_constructor_id", "constructor_champion_id"
    )

    summary_columns = [
        "year",
        "constructor_champion_id",
        "constructor_champion",
        "constructor_champion_points",
        "driver_champion_id",
        "driver_champion",
        "driver_champion_points",
        "driver_champion_primary_constructor_id",
        "driver_champion_primary_constructor",
        "driver_champion_primary_constructor_points_share",
        "driver_champion_primary_constructor_won_constructors_title",
        "qualifying_fastest_constructor_id",
        "qualifying_fastest_constructor",
        "qualifying_fastest_races",
        "qualifying_races_available",
        "qualifying_avg_gap_pct",
        "qualifying_fastest_is_constructor_champion",
        "fastest_lap_fastest_constructor_id",
        "fastest_lap_fastest_constructor",
        "fastest_lap_fastest_races",
        "fastest_lap_races_available",
        "fastest_lap_avg_gap_pct",
        "fastest_lap_fastest_is_constructor_champion",
        "race_win_leader_constructor_id",
        "race_win_leader_constructor",
        "race_wins",
        "races_with_winner",
        "race_win_leader_is_constructor_champion",
    ]
    summary[summary_columns].to_csv(OUT / "yearly_fastest_car_summary.csv", index=False)

    inventory_rows = []
    for source, folder in [("f1db", F1DB), ("tracinginsights", TRACING)]:
        for csv_path in sorted(folder.glob("*.csv")):
            frame = pd.read_csv(csv_path, nrows=0)
            rows = sum(1 for _ in csv_path.open("rb")) - 1
            inventory_rows.append(
                {
                    "source": source,
                    "file": csv_path.name,
                    "rows": rows,
                    "columns": len(frame.columns),
                    "column_names": "|".join(frame.columns),
                }
            )
    pd.DataFrame(inventory_rows).to_csv(OUT / "data_inventory.csv", index=False)

    ti_lap_times = read_tracing("lap_times.csv", usecols=["raceId"])
    ti_races = read_tracing("races.csv", usecols=["raceId", "year"])
    ti_lap_years = ti_lap_times.merge(ti_races, on="raceId", how="left")["year"].dropna()

    def match_rate(column: str) -> str:
        valid = summary[column].dropna()
        if valid.empty:
            return "n/a"
        matches = int(valid.astype(bool).sum())
        total = int(valid.count())
        return f"{matches / total:.1%} ({matches}/{total})"

    stats = [
        "F1 all-time starter analysis",
        "",
        f"F1DB release files cover seasons {int(seasons['year'].min())}-{int(seasons['year'].max())}.",
        f"F1DB races: {races['id'].nunique():,}",
        f"F1DB race result rows: {len(race_results):,}",
        f"F1DB qualifying result rows: {len(qualifying):,}",
        f"F1DB fastest-lap rows: {len(fastest_laps):,}",
        f"TracingInsights lap-time rows: {len(ti_lap_times):,}",
        (
            "TracingInsights lap-time coverage years: "
            f"{int(ti_lap_years.min())}-{int(ti_lap_years.max())}"
        ),
        "",
        "Constructor title match rates where a constructor champion exists:",
        f"Qualifying proxy leader == constructor champion: {match_rate('qualifying_fastest_is_constructor_champion')}",
        f"Fastest-lap proxy leader == constructor champion: {match_rate('fastest_lap_fastest_is_constructor_champion')}",
        f"Race-win leader == constructor champion: {match_rate('race_win_leader_is_constructor_champion')}",
        (
            "Driver champion's primary constructor == constructor champion: "
            f"{match_rate('driver_champion_primary_constructor_won_constructors_title')}"
        ),
        "",
        "Generated files:",
        "analysis/yearly_fastest_car_summary.csv",
        "analysis/driver_points_within_constructor.csv",
        "analysis/data_inventory.csv",
    ]
    (OUT / "summary_stats.txt").write_text("\n".join(stats) + "\n", encoding="utf-8")

    print("\n".join(stats))


if __name__ == "__main__":
    main()
