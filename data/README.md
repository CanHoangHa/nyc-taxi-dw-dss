# Data directory

The [CO4031 Group 10 sample data folder](https://drive.google.com/drive/folders/1Ca045Gt2O17jTH5IH1ifB-tucfD3rOmI?usp=sharing) is the submission link for these files:

- `yellow_tripdata_2024-01.parquet` contains the January 2024 trips. Place it in
  `data/raw/yellow/2024/01/` relative to the project root. In the submission ZIP,
  the full path from the ZIP root is `src/data/raw/yellow/2024/01/`.
- `taxi_zone_lookup.csv` contains the TLC taxi zone reference. The project
  already includes this file at `src/dbt/seeds/taxi_zone_lookup.csv` relative
  to the project root.

The report's forecasting and evaluation use January through April 2024. For
the remaining months, see step 2 of the project README (`src/README.md` in the
submission ZIP). Keep monthly Parquet files under the Git-ignored `data/raw/`
directory.
