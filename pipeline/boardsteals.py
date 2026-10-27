import os
import json
import math
import pandas as pd
import nflreadpy as nfl
from datetime import datetime

# --- CONFIGURATION ---
DATA_DIR = "../site/public/data"

# Only the play-by-play columns needed for end zone targets (the full table has ~370)
PBP_COLS = ["week", "pass_attempt", "air_yards", "yardline_100", "receiver_player_id"]

# Dynamic Season Setup
SEASON = datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1
IS_SEASON_ACTIVE = datetime.now().month in [9, 10, 11, 12, 1]

def setup_directories():
    os.makedirs(DATA_DIR, exist_ok=True)

def load_pbp(season):
    return nfl.load_pbp(seasons=[season]).select(PBP_COLS).to_pandas()

# Buy-low projection: blend of recent usage and recent output (weights fitted on 2023-24 data)
WINDOW = 3
XP_WEIGHT = 0.6

def calculate_ratings(df):
    # df holds every game of the season so far; ratings only use games up to each row's week
    VALID_POSITIONS = ["QB", "RB", "WR", "TE"]
    df = df[df["position"].isin(VALID_POSITIONS)].copy()

    # 1. Ensure all expected columns exist (fills with 0 if missing)
    expected_cols = [
        'attempts', 'passing_air_yards', 'passing_tds', 'passing_yards', 'passing_interceptions',
        'carries', 'rushing_yards', 'rushing_tds',
        'targets', 'receiving_air_yards', 'receptions', 'receiving_yards', 'receiving_tds',
        'wopr', 'endzone_targets'
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = 0
    df[expected_cols] = df[expected_cols].fillna(0)

    # 2. Calculate Actual Fantasy Points (Standard 4pt passing TD, PPR)
    df['actual_points'] = (
        (df['passing_yards'] * 0.04) + (df['passing_tds'] * 4.0) - (df['passing_interceptions'] * 2.0) +
        (df['rushing_yards'] * 0.1) + (df['rushing_tds'] * 6.0) +
        (df['receptions'] * 1.0) + (df['receiving_yards'] * 0.1) + (df['receiving_tds'] * 6.0)
    )

    # 3. Calculate Expected Fantasy Points based on league-average positional usage
    df['expected_points'] = (
        (df['attempts'] * 0.42) +             # Passing volume
        (df['passing_air_yards'] * 0.03) +    # Passing depth opportunity
        (df['carries'] * 0.70) +              # Rushing volume
        (df['targets'] * 0.80) +              # Receiving volume 
        (df['receiving_air_yards'] * 0.06) +  # Receiving depth opportunity
        (df['wopr'] * 4.0) +                  # Market share weight (mostly WR/RB/TE)
        (df['endzone_targets'] * 2.0)         # End Zone Target Bonus
    )

    # Opportunities, used for the noise floor
    df['total_opportunity'] = df['attempts'] + df['carries'] + df['targets']

    # 4. Buy-low score: projected points from the last few games minus the player's season average so far
    df = df.sort_values(['player_id', 'week'])
    games = df.groupby('player_id')
    df['recent_xp'] = games['expected_points'].transform(lambda x: x.rolling(WINDOW, min_periods=1).mean())
    df['recent_act'] = games['actual_points'].transform(lambda x: x.rolling(WINDOW, min_periods=1).mean())
    df['season_avg'] = games['actual_points'].transform(lambda x: x.expanding().mean())
    df['buy_low_score'] = XP_WEIGHT * df['recent_xp'] + (1 - XP_WEIGHT) * df['recent_act'] - df['season_avg']

    # Only rate players with real volume this week (history above still counts their quieter games)
    active_mask = (df['total_opportunity'] >= 2) | (df['expected_points'] >= 3.0)
    df = df[active_mask].copy()

    # Positional z-score within each week
    df['z_score'] = df.groupby(['week', 'position'])['buy_low_score'].transform(
        lambda x: (x - x.mean()) / x.std()
    )

    # Handle NaNs for positions with only 1 player or identical stats (0 standard deviation)
    df['z_score'] = df['z_score'].fillna(0)

    # 5. Map z onto the rating scale; 13 per SD puts Diamond (99+) at roughly the top 0.1%
    df['rating'] = ((df['z_score'] * 13) + 54).clip(1.0, 99.9).round(1)

    return df

def format_player_json(row):
    pos = row['position']

    # Ask the NFL image CDN for a card-sized copy instead of the ~1MB original
    headshot_url = row.get('headshot_url')
    if isinstance(headshot_url, str):
        headshot_url = headshot_url.replace("/f_auto,q_auto/", "/f_auto,q_auto,w_512/")


    # Dynamic stats based on position
    if pos == "QB":
        detail_stats = [
            {"label": "Pass Att", "value": int(row.get('attempts', 0))},
            {"label": "Pass Yds", "value": int(row.get('passing_yards', 0))},
            {"label": "Pass TDs", "value": int(row.get('passing_tds', 0))},
            {"label": "Carries", "value": int(row.get('carries', 0))},
            {"label": "Rush Yds", "value": int(row.get('rushing_yards', 0))},
            {"label": "INTs", "value": int(row.get('passing_interceptions', 0))}
        ]
    else: # RB, WR, TE
        detail_stats = [
            {"label": "Targets", "value": int(row.get('targets', 0))},
            {"label": "Carries", "value": int(row.get('carries', 0))},
            {"label": "Receptions", "value": int(row.get('receptions', 0))},
            {"label": "Rec Yds", "value": int(row.get('receiving_yards', 0))},
            {"label": "Rush Yds", "value": int(row.get('rushing_yards', 0))},
            {"label": "WOPR", "value": round(float(row.get('wopr', 0)), 2) if 'wopr' in row and not pd.isna(row['wopr']) else 0}
        ]

    return {
        "id": row['player_id'],
        "name": row['player_display_name'],
        "team": row.get('team', row.get('recent_team', 'UNK')),
        "position": pos,
        "week": int(row['week']),
        "rating": float(row['rating']),
        "headshot": headshot_url,
        "main_stats": {
            # The numbers the rating is built from: last-3-game averages vs season average
            "expected_points": round(float(row['recent_xp']), 1),
            "actual_points": round(float(row['recent_act']), 1),
            "season_avg": round(float(row['season_avg']), 1)
        },
        "detail_stats": detail_stats
    }

def sanitize_nan(obj):
    # Clean broken data points in json
    if isinstance(obj, dict):
        return {k: sanitize_nan(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize_nan(v) for v in obj]
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj

def main():
    global SEASON, IS_SEASON_ACTIVE 
    print(f"Fetching LIVE NFL Data for {SEASON} using nflreadpy...")
    setup_directories()
    
    # 1. Fetch live data natively
    try:
        weekly_df = nfl.load_player_stats(seasons=[SEASON]).to_pandas()
        pbp_df = load_pbp(SEASON) # Fetch PBP for end zone targets
        if weekly_df.empty or pbp_df.empty:
            raise ValueError("Data exists but is empty.")
    except Exception as e:
        print(f"!! Live data for {SEASON} not found yet (Week 1 stats pending).")
        print(f"Falling back to {SEASON - 1}...")
        SEASON -= 1
        IS_SEASON_ACTIVE = False
        weekly_df = nfl.load_player_stats(seasons=[SEASON]).to_pandas()
        pbp_df = load_pbp(SEASON)

    # 2. Cleanup and filter
    cols_to_fill = ['carries', 'targets', 'receptions', 'receiving_yards', 'rushing_yards', 'fantasy_points_ppr']
    for c in cols_to_fill:
        if c in weekly_df.columns:
            weekly_df[c] = pd.to_numeric(weekly_df[c], errors='coerce').fillna(0)
      
    latest_week = int(weekly_df['week'].max())
    print(f"Processing data up to Week {latest_week} of {SEASON}...")
    
    pbp_df["is_endzone_target"] = (
        (pbp_df["pass_attempt"] == 1) & 
        (pbp_df["air_yards"] >= pbp_df["yardline_100"])
    ).astype(int)
    
    # Sum end zone targets per receiver per week
    ez_targets = pbp_df.groupby(["week", "receiver_player_id"])["is_endzone_target"].sum().reset_index()
    ez_targets.columns = ["week", "player_id", "endzone_targets"]
    
    # Merge the calculated end zone targets into the weekly summary stats
    weekly_df = weekly_df.merge(ez_targets, on=["week", "player_id"], how="left").fillna({"endzone_targets": 0})

    # Rate every week of the season; the weekly board is the latest week, the global board all weeks
    df = calculate_ratings(weekly_df).sort_values(by="rating", ascending=False)
    top_50 = df[df["week"] == latest_week].head(50)
    
    print("Formatting Weekly JSON...")
    weekly_players = [format_player_json(row) for _, row in top_50.iterrows()]
    
    meta_block = {
        "is_season_active": IS_SEASON_ACTIVE,
        "season": SEASON,
        "last_completed_season": SEASON - 1 if IS_SEASON_ACTIVE else SEASON,
        "current_week": latest_week
    }
    
    # 3. Save JSON files
    weekly_output = sanitize_nan({"meta": meta_block, "players": weekly_players})
    with open(f"{DATA_DIR}/picks_weekly.json", "w") as f:
        json.dump(weekly_output, f, indent=2)
        
    # Top 50 single-week ratings of the season; the same player can appear once per week
    global_players = [format_player_json(row) for _, row in df.head(50).iterrows()]
    global_output = sanitize_nan({"meta": meta_block, "players": global_players})
    with open(f"{DATA_DIR}/picks_global.json", "w") as f:
        json.dump(global_output, f, indent=2)

    print("Pipeline complete. JSON is synced.")

if __name__ == "__main__":
    main()