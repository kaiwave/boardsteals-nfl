import os
import json
import math
import requests
import pandas as pd
import numpy as np
import nflreadpy as nfl
from datetime import datetime

# --- CONFIGURATION ---
DATA_DIR = "../site/public/data"
ASSETS_DIR = "../site/public/assets/headshots"

# Dynamic Season Setup
SEASON = datetime.now().year if datetime.now().month > 6 else datetime.now().year - 1
IS_SEASON_ACTIVE = datetime.now().month in [9, 10, 11, 12, 1]

def setup_directories():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ASSETS_DIR, exist_ok=True)

def download_headshot(player_id, url):
    if not isinstance(url, str) or not url.startswith("http"):
        return None
    
    file_path = f"{ASSETS_DIR}/{player_id}.png"
    local_path = f"/assets/headshots/{player_id}.png"
    
    if not os.path.exists(file_path):
        try:
            # Spoof a real browser to bypass ESPN's anti-bot blocking
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            r = requests.get(url, headers=headers, timeout=5)
            if r.status_code == 200:
                with open(file_path, 'wb') as f:
                    f.write(r.content)
            else:
                return None
        except Exception as e:
            print(f"Failed to download {player_id}: {e}")
            return None
    return local_path

def calculate_ratings(df):
    df = df[df['position'].isin(['RB', 'WR', 'TE'])].copy()
    
    # Ensure advanced metrics exist (fill with 0 for players who only run the ball)
    df['wopr'] = pd.to_numeric(df.get('wopr', 0), errors='coerce').fillna(0)
    df['receiving_air_yards'] = pd.to_numeric(df.get('receiving_air_yards', 0), errors='coerce').fillna(0)
    
    # --- MORE ADVANCED EXPECTED PPR FORMULA ---
    # Rushing: Retains the 0.7 baseline per carry
    # Baseline Receiving: 0.8 pts per target (represents floor value of dump-offs)
    # Advanced Receiving (Air Yards): 0.06 pts per air yard (values deep threats)
    # Team Dominance (WOPR): A flat +4.0 modifier multiplied by their WOPR percentage to reward alpha receivers
    df['expected_ppr'] = (
        (df.get('carries', 0) * 0.7) + 
        (df.get('targets', 0) * 0.8) + 
        (df['receiving_air_yards'] * 0.06) + 
        (df['wopr'] * 4.0)
    )
    
    df['disparity'] = df['expected_ppr'] - df.get('fantasy_points_ppr', 0)
    
    # Filter out bench warmers to avoid noisy data (min 6.0 expected points)
    df = df[df['expected_ppr'] >= 6.0] 
    
    disp = df['disparity']
    z = (disp - disp.mean()) / disp.std()
    
    df['z_score'] = z
    df['rating'] = np.clip(54 + (z * 14), 0, 100).round(1)
    
    return df.sort_values('rating', ascending=False)

def format_player_json(row):
    headshot_path = download_headshot(row['player_id'], row.get('headshot_url'))
    
    return {
        "id": row['player_id'],
        "name": row['player_display_name'],
        "team": row.get('team', row.get('recent_team', 'UNK')),
        "position": row['position'],
        "week": int(row['week']),
        "rating": float(row['rating']),
        "headshot": headshot_path,
        "main_stats": {
            "expected_points": round(float(row['expected_ppr']), 1),
            "actual_points": round(float(row.get('fantasy_points_ppr', 0)), 1),
            "total_opportunity": int(row.get('carries', 0) + row.get('targets', 0))
        },
        "detail_stats": {
            "targets": int(row.get('targets', 0)),
            "carries": int(row.get('carries', 0)),
            "receptions": int(row.get('receptions', 0)),
            "receiving_yards": int(row.get('receiving_yards', 0)),
            "rushing_yards": int(row.get('rushing_yards', 0)),
            "wopr": round(float(row.get('wopr', 0)), 2) if 'wopr' in row and not pd.isna(row['wopr']) else 0
        }
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

def cleanup_unused_headshots(active_player_ids):
    if not os.path.exists(ASSETS_DIR):
        return
        
    valid_filenames = {f"{pid}.png" for pid in active_player_ids}
    removed_count = 0
    
    for filename in os.listdir(ASSETS_DIR):
        if filename.endswith(".png") and filename not in valid_filenames:
            file_path = os.path.join(ASSETS_DIR, filename)
            try:
                os.remove(file_path)
                removed_count += 1
            except Exception as e:
                print(f"Failed to delete {filename}: {e}")
                
    if removed_count > 0:
        print(f"Cleaned up {removed_count} stale headshots.")

def main():
    global SEASON, IS_SEASON_ACTIVE 
    print(f"Fetching LIVE NFL Data for {SEASON} using nflreadpy...")
    setup_directories()
    
# 1. Fetch live data natively
    try:
        weekly_df = nfl.load_player_stats(seasons=[SEASON]).to_pandas()
        if weekly_df.empty:
            raise ValueError("Data exists but is empty.")
    except Exception as e:
        print(f"!! Live data for {SEASON} not found yet (Week 1 stats pending).")
        print(f"Falling back to {SEASON - 1}...")
        SEASON -= 1
        IS_SEASON_ACTIVE = False
        weekly_df = nfl.load_player_stats(seasons=[SEASON]).to_pandas()

    # 2. Cleanup and filter
    cols_to_fill = ['carries', 'targets', 'receptions', 'receiving_yards', 'rushing_yards', 'fantasy_points_ppr']
    for c in cols_to_fill:
        if c in weekly_df.columns:
            weekly_df[c] = pd.to_numeric(weekly_df[c], errors='coerce').fillna(0)
      
    latest_week = int(weekly_df['week'].max())
    print(f"Processing data up to Week {latest_week} of {SEASON}...")
    
    current_week_df = weekly_df[weekly_df['week'] == latest_week].copy() 

    rated_df = calculate_ratings(current_week_df)
    top_50 = rated_df.head(50)
    
    print("Formatting Weekly JSON and downloading headshots...")
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
        
    global_path = f"{DATA_DIR}/picks_global.json"
    global_players = []
    
    if os.path.exists(global_path):
        with open(global_path, "r") as f:
            try:
                global_data = json.load(f)
                global_players = global_data.get("players", [])
            except json.JSONDecodeError:
                pass
                
    all_time_df = pd.DataFrame(global_players + weekly_players)
    if not all_time_df.empty:
        all_time_df = all_time_df.sort_values('rating', ascending=False)
        all_time_df = all_time_df.drop_duplicates(subset=['id'], keep='first')
        
        top_50_global = all_time_df.head(50).to_dict('records')
        global_output = sanitize_nan({"meta": meta_block, "players": top_50_global})
        with open(global_path, "w") as f:
            json.dump(global_output, f, indent=2)

    active_ids = {p['id'] for p in weekly_players} | {p['id'] for p in top_50_global}
    cleanup_unused_headshots(active_ids)

    print("Pipeline complete. JSON and assets are synced.")

if __name__ == "__main__":
    main()