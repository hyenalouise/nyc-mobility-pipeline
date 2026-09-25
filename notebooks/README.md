# Notebooks

Notebooks in this folder are for source profiling and focused investigation:

| Notebook | Purpose |
|---|---|
| `profile_green_taxi.ipynb` | Green Taxi schema, null, range, and duplicate exploration |
| `profile_weather.ipynb` | Open-Meteo response, time, coverage, and anomaly exploration |
| `join_coverage_analysis.ipynb` | Zone and weather relationship coverage analysis |

They are not the production pipeline. Production transformations live in
`etl/`, source gates live in `src/ingestion/`, and orchestration lives in
`databricks.yml`.

Before committing a notebook:

- clear data-bearing output;
- remove tokens, credentials, and local paths;
- keep the notebook focused on investigation rather than production logic;
- move accepted rules into the canonical config, SQL, or documentation;
- confirm it remains under `notebooks/`, the only approved `.ipynb` location.
