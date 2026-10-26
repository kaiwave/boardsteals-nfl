# Boardsteals
An automated NFL fantasy pipeline that identifies buy-low candidates, waiver wire gems, and board steals by evaluating the disparity between offensive volume (opportunity) and box-score fantasy output.

Live site: [boardsteals.kaiwave.dev](https://boardsteals.kaiwave.dev)

--- 

## The Model
Traditional fantasy platforms rank players by raw fantasy points, which heavily reflect trailing results, touchdown luck, and splash plays. Boardsteals inverts this by prioritising underlying offensive opportunity.

### Step 1: Expected Points and Intra-Positional Disparity (Advanced Opportunity Baseline)
Traditional metrics treat all targets equally, but we do not. Boardsteals evaluates opportunity using advanced tracking metrics like Air Yards and WOPR (Weighted Opportunity Rating) to weigh exactly *how* a player is being used in their specific roles, and compares players strictly against their positional peers.

$$\begin{aligned} 
\text{Expected Points} & = (\text{Pass Att} \times 0.42) \\
& + (\text{Pass Air Yards} \times 0.03) \\ 
& + (\text{Carries} \times 0.70) \\ 
& + (\text{Targets} \times 0.80) \\
& + (\text{Rec Air Yards} \times 0.06) \\  
& + (\text{WOPR} \times 4.0) \\
& + (\text{End Zone Targets} \times 2.0) 
\end{aligned}$$

- Passing Volume & Depth ($0.42$ / $0.03$ pts): Accounts for quarterback pass attempts and downfield air-yard equity, modeling league-average completion rates and yardage expectation per dropback.

- Carries ($0.7$) pt Accounts for historical league-average yards per carry plus goal-line touchdown equity.
  
- Baseline Targets ($0.8$ pts): The baseline PPR value of commanding a target, regardless of depth.

- Air Yards ($0.06$ pts): Evaluates depth of target (aDOT). A player seeing 5 targets 20 yards down the field generates significantly more expected fantasy points than a player seeing 5 passes behind the line of scrimmage. 

- WOPR Multiplier ($4.0$ modifier): WOPR combines a player's raw target share with their team air yards share. Scaling this metric rewards true "alpha" receivers who dominate their team's offensive game plan, filtering out random depth players who caught a lucky deep pass.

- End Zone Targets ($2.0$ multiplier): An end zone target already gets counted in Targets (+0.80) and receives a small contribution from Rec Air Yards. This term adds a bonus as incompletes in the endzone are worth more than elsewhere. 

### Step 2: Disparity Calculation
We evaluate whether a player's fantasy output underperformed or outpaced their real-world usage,

$$\text{Disparity} = \text{Expected Points} - \text{Actual Fantasy Points}$$

$$\text{Z-Score}_{\text{Pos}} = \frac{\text{Disparity} - \mu_{\text{position}}}{\sigma_{\text{position}}}$$

Which gives us key outcomes:

- High Positive Disparity: High-volume involvement that was stalled by bad goal-line variance, tipped passes, or defensive stops. These players are prime candidates for breakout games (underrated).

- Negative Disparity: Low-volume involvement inflated by unsustainable 70-yard breakaways or fluke multi-touchdown box scores (overrated).

- Intra-Positional Grouping: Because quarterback volume naturally outpaces flex positions, Z-scores are computed strictly within each position group ($\text{QB}$, $\text{RB}$, $\text{WR}$, $\text{TE}$). A top-tier rating reflects an elite usage-to-output gap relative to positional peers.

### Step 3: Noise Threshold
To eliminate backup players and gadget options who distort small-sample statistics (e.g., a WR5 running one route, seeing one target, and dropping it for a $+1.8$ disparity), the engine requires a minimum opportunity floor

$$\text{Opportunities} \ge 2 \quad \text{or} \quad \text{Expected PPR} \ge 3.0$$

where Opportunities = pass attempts + carries + targets.

### Step 4: Normalisation (The Boardsteals rating)
To translate disparity into an intuitive rating where the league median sits in the 50–60 range, disparity values are normalised using the positional Z-scores from Step 2 across the active weekly sample,

$$Z = \frac{\text{Disparity} - \mu_{\text{position}}}{\sigma_{\text{position}}}$$

And given a Boardsteals rating from 1-99.9 accordingly.

$$\text{Rating} = \text{clip}\left(54 + (Z \times 14),\, 1,\, 99.9\right)$$

- Rating $0-55$ - Iron: Up to just above median expectation ($Z = 0$). Output closely matched volume.
  
- Rating $56–70$ - Bronze: Some positive disparity. Between the top 47-13% most underrated players.
  
- Rating $71-80$ - Silver: High positive disparity. Between the top 13-3% most underrated players

- Rating $81-97$ - Gold: Extremely high potential players, top 3% most underrated players in the league.

- Rating $98+$ - Diamond: Projected skill underpaced actual points by multiple standard deviations. Top 0.1% generational outliers. 

---

## Architecture and Pipeline
The backend script (`pipeline/boardsteals.py`) runs as a fully decoupled, zero-server data generation pipeline.

```
[nflreadpy API]
           │
           ▼
[Data Extraction & Polars-to-Pandas Conversion (only the needed pbp columns)]
           │
           ▼
[Position Filtering (QB/RB/WR/TE)]
           │
           ▼
[xP and Disparity Calculation]
           │
           ▼
[Noise Filtering (Opportunities >= 2 or Exp PPR >= 3.0)]
           │
           ▼
[Z-Score Calculation & Rating Engine (1-99.9)]
           │
           ▼
[JSON Serialization] ───────────► [site/public/data/picks_weekly.json]
           │                  └─► [site/public/data/picks_global.json]
           ▼
[Site Deployment] ──────────────► Clear Cloudflare CDN Cache and deploy the updated lists
```

---

### Key Modules
- Dynamic Season Ingestion: Uses nflreadpy to ingest official weekly NFL player box scores and pbp stats. The engine isolates the latest completed week (`week.max()`) and provides fallback recovery to the previous season if the current season's data is not available yet.
  
- Headshots: The JSON stores each player's official headshot URL from nflreadpy, and the browser loads it directly from that CDN. Nothing is downloaded or stored in the repo.

- Dual-Board JSON Serialization:

- - `picks_weekly.json`: The Top 50 rated players from the current week's games.

- - `picks_global.json`: The season leaderboard: the Top 50 single-week ratings so far. The same player can appear once per week. It is cleared when Week 1 of a new season is processed.

- Cloudflare CDN Cache: Optimise GitHub pages bandwidth by caching the site and team logos on Cloudflare's CDN, purging once a week during the automated run.

---

## Data
Since the live site is run on a github pages instance, the pipeline exports static JSON files consumable by static site generators without runtime database calls. For example,

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
      "headshot": "https://static.www.nfl.com/image/upload/f_auto,q_auto,w_512/league/<image-id>",
      "main_stats": {
        "expected_points": 9.0,
        "actual_points": 4.6,
        "total_opportunity": 5
      },
      "detail_stats": [
        { "label": "Targets", "value": 5 },
        { "label": "Carries", "value": 0 },
        { "label": "Receptions", "value": 2 },
        { "label": "Rec Yds", "value": 26 },
        { "label": "Rush Yds", "value": 0 },
        { "label": "WOPR", "value": 0.37 }
      ]
    }
  ]
}
```

---

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

The script will fetch the latest data, normalise scores, and write the formatted data to `site/public/data/`.

Enjoy your fantasy pickings!

---
[MIT License](LICENSE)
