# Boardsteals
An automated NFL fantasy pipeline that identifies buy-low candidates, waiver wire gems, and board steals by evaluating the disparity between offensive volume (opportunity) and box-score fantasy output.

Live site: [boardsteals.kaiwave.dev](https://boardsteals.kaiwave.dev)

## The Model
Traditional fantasy platforms rank players by raw fantasy points, which heavily reflect trailing results, touchdown luck, and splash plays. Boardsteals inverts this by prioritising underlying offensive opportunity.

### Step 1: Expected Points and Intra-Positional Disparity (Advanced Opportunity Baseline)
Traditional metrics treat all targets equally, but we do not. Boardsteals evaluates opportunity using advanced tracking metrics like Air Yards and WOPR (Weighted Opportunity Rating) to weigh exactly *how* a player is being used in their specific roles, and compares players strictly against their positional peers.

$$\begin{aligned} \text{Expected Points} &= (\text{Pass Att} \times 0.42) + (\text{Pass Air Yards} \times 0.03) \\ &+ (\text{Carries} \times 0.70) \\ &+ (\text{Targets} \times 0.80) + (\text{Rec Air Yards} \times 0.06) + (\text{WOPR} \times 4.0) \end{aligned}$$

- Passing Volume & Depth ($0.42$ / $0.03$ pts): Accounts for quarterback pass attempts and downfield air-yard equity, modeling league-average completion rates and yardage expectation per dropback.

- Carries ($0.7$) pt Accounts for historical league-average yards per carry plus goal-line touchdown equity.
  
- Baseline Targets ($0.8$ pts): The baseline PPR value of commanding a target, regardless of depth.

- Air Yards ($0.06$ pts): Evaluates depth of target (aDOT). A player seeing 5 targets 20 yards down the field generates significantly more expected fantasy points than a player seeing 5 passes behind the line of scrimmage. 

- WOPR Multiplier ($4.0$ modifier): WOPR combines a player's raw target share with their team air yards share. Scaling this metric rewards true "alpha" receivers who dominate their team's offensive game plan, filtering out random depth players who caught a lucky deep pass.

### Step 1: Disparity Calculation
We evaluate whether a player's fantasy output underperformed or outpaced their real-world usage,

$$\text{Disparity} = \text{Expected Points} - \text{Actual Fantasy Points}$$

$$\text{Z-Score}_{\text{Pos}} = \frac{\text{Disparity} - \mu_{\text{position}}}{\sigma_{\text{position}}}$$

Which gives us key outcomes:

- High Positive Disparity: High-volume involvement that was stalled by bad goal-line variance, tipped passes, or defensive stops. These players are prime candidates for breakout games (underrated).

- Negative Disparity: Low-volume involvement inflated by unsustainable 70-yard breakaways or fluke multi-touchdown box scores (overrated).

- Intra-Positional Grouping: Because quarterback volume naturally outpaces flex positions, Z-scores are computed strictly within each position group ($\text{QB}$, $\text{RB}$, $\text{WR}$, $\text{TE}$). A top-tier rating reflects an elite usage-to-output gap relative to positional peers.

### Step 3: Noise Threshold
To eliminate backup players and gadget options who distort small-sample statistics (e.g., a WR5 running one route, seeing one target, and dropping it for a $+1.8$ disparity), the engine requires a minimum opportunity floor

$$\text{Expected PPR} \ge 6.0$$ 

(Equivalent to roughly 4+ targets, 9+ carries, or a hybrid workload).

### Step 4: Normalisation (The Boardsteals rating)
To translate disparity into an intuitive rating where the league median sits in the 50–60 range, disparity values are normalised using standard Z-scores across the active weekly sample,

$$Z = \frac{\text{Disparity} - \mu}{\sigma}$$

And given a Boardsteals rating from 0-100 accordingly.

$$\text{Rating} = \text{clip}\left(54 + (Z \times 14),\, 0,\, 100\right)$$

- Rating $0-55$ - Iron: Up to just above median expectation ($Z = 0$). Output closely matched volume.
  
- Rating $56–70$ - Bronze: Some positive disparity. Between the top 47-13% most underrated players.
  
- Rating $71-80$ - Silver: High positive disparity. Between the top 13-3% most underrated players

- Rating $81-97$ - Gold: Extremely high potential players, top 3% most underrated players in the league.

- Rating $98+$ - Diamond: Projected skill underpaced actual points by multiple standard deviations. Top 0.1% generational outliers. 

## Architecture and Pipeline
The backend script (`pipeline/boardsteals.py`) runs as a fully decoupled, zero-server data generation pipeline.

```
[nflverse / nflreadpy API]
           │
           ▼
[Data Extraction & Polars-to-Pandas Conversion]
           │
           ▼
[Position & Noise Filtering (RB/WR/TE; Exp PPR >= 6.0)]
           │
           ▼
[Z-Score Calculation & Rating Engine (0-100)]
           │
           ▼
[Headshot Download Manager] ────► [Local Asset Cache: site/public/assets/headshots/]
           │                       (Requests session, browser headers, 0.5s rate-limit)
           ▼
[JSON Serialization] ───────────► [site/public/data/picks_weekly.json]
           │                  └─► [site/public/data/picks_global.json]
           ▼
[Garbage Collection] ───────────► Prunes stale images not present in Weekly or Global Top 50
```

### Key Modules
- Dynamic Season Ingestion: Uses nflreadpy to ingest official weekly NFL player box scores. The engine isolates the latest completed week (`week.max()`) and provides fallback recovery if an active week's dataset is pending ingestion.
  
- Headshot Asset Cache: Downloads official player portraits directly to `site/public/assets/headshots/{player_id}.png`.

- - Checks `os.path.exists()` before requesting to avoid redundant network calls.

- Dual-Board JSON Serialization:

- - `picks_weekly.json`: The Top 50 rated players from the current week's games.

- - `picks_global.json`: The all-time season leaderboard. Deduplicates multiple weeks for the same player, retaining only their highest-rated single-game breakout signal.

- Garbage Collection Pruning: Automatically deletes cached .png files from disk if a player drops out of both the Weekly Top 50 and the Global Top 50, capping local disk usage to ~100 images maximum.

## Data
Since this will be run on a github pages instance, the pipeline exports static JSON files consumable by static site generators without runtime database calls. For example,

```
{
  "meta": {
    "is_season_active": true,
    "season": 2026,
    "last_completed_season": 2025,
    "current_week": 2
  },
  "players": [
    {
      "id": "00-0040669",
      "name": "Isaac TeSlaa",
      "team": "DET",
      "position": "WR",
      "week": 2,
      "rating": 71.0,
      "headshot": "/assets/headshots/00-0040669.png",
      "main_stats": {
        "expected_points": 9.0,
        "actual_points": 4.6,
        "total_opportunity": 5
      },
      "detail_stats": {
        "targets": 5,
        "carries": 0,
        "receptions": 2,
        "receiving_yards": 26,
        "rushing_yards": 0,
        "wopr": 0.37
      }
    }
  ]
}
```

## Setup
The python scripts can be found in `pipeline`, and you can tweak the parameters and equations to suit your team's needs. 

### Prerequisites
Python 3.10+

### Installation
1. Clone the repository and navigate to the pipeline directory:
```
cd pipeline
```

2. Install dependencies:
```
pip install -r requirements.txt --prefer-binary
```

3. Execute pipeline:
```
python boardsteals.py
```

The script will fetch the latest data, normalise scores, download any missing headshots to `site/public/assets/headshots/`, and write the formatted data to `site/public/data/`.

Enjoy your fantasy pickings!
