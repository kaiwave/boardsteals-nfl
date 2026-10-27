# Self-check for calculate_ratings: run with `python test_ratings.py` from the pipeline folder
import pandas as pd
from boardsteals import calculate_ratings


def game(pid, week, targets, rec_yds, receptions, tds=0):
    return {"player_id": pid, "position": "WR", "week": week, "targets": targets,
            "receiving_air_yards": targets * 10, "receptions": receptions,
            "receiving_yards": rec_yds, "receiving_tds": tds, "wopr": targets / 20}


rows = []
for week in [1, 2, 3]:
    # Busy WR who produced in weeks 1-2 but was shut out in week 3: a buy-low
    rows.append(game("busy", week, 10, 0 if week == 3 else 90, 0 if week == 3 else 7))
    # Low-usage WR who lucked into a TD in week 3: a sell
    rows.append(game("lucky", week, 3, 60 if week == 3 else 20, 2, tds=1 if week == 3 else 0))
    # Steady fillers so the positional z-score has a spread
    for i in range(6):
        rows.append(game(f"filler{i}", week, 5 + i, 40 + 5 * i, 3 + i // 2))

season = pd.DataFrame(rows)
rated = calculate_ratings(season).set_index(["player_id", "week"])["rating"]

assert rated[("busy", 3)] > 54 > rated[("lucky", 3)], rated.xs(3, level="week")

# Ratings only use past games: adding week 3 must not change week 2
through_week_2 = calculate_ratings(season[season.week <= 2]).set_index(["player_id", "week"])["rating"]
assert rated.xs(2, level="week").equals(through_week_2.xs(2, level="week"))

print("calculate_ratings self-check passed")
