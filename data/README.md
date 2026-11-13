# Data directory

The official Taxi Zone Lookup is stored in `reference/`. Monthly trip data may
be downloaded locally under `raw/`, which is excluded from Git.

- `sample/` will contain only small samples suitable for Git and the university
  submission.
- `reference/taxi_zone_lookup.csv` is the small shared TLC zone reference.
- `raw/yellow/2024/01/` is the expected local location for the January vertical
  slice.
- Full monthly NYC TLC Yellow Taxi Parquet files stay in the Git-ignored local
  raw-data directory.

Full raw trip data must not be committed to Git. Source URLs, checksums, and
profile evidence are documented under `docs/profiles/`.
