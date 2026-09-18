# Sleepers
NFL fantasy sleeper picks, based on underlying hidden data. 

Will be built fairly quick since its already week 2. Let me lock in.

## Repository Structure
```
sleeper-picks-py/
├── .github/
│   └── workflows/
│       └── weekly_run.yml    # Runs Python script -> builds & deploys site
├── pipeline/
│   ├── boardsteals.py           # Scrapes nfl_data_py & cross-references Sleeper
│   └── requirements.txt
├── site/                     # Source code for frontend site
│   ├── public/
│   │   └── data/
│   │       └── picks.json    # Written directly by boardsteals.py
│   ├── src/
│   └── package.json
└── README.md
```