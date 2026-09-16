"""Source naming and path rules for the project dataset."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


TLC_TRIP_DATA_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


@dataclass(frozen=True, slots=True)
class YellowTaxiSource:
    """One monthly Yellow Taxi source artifact in the frozen 2024 scope."""

    year: int
    month: int

    def __post_init__(self) -> None:
        if self.year != 2024:
            raise ValueError("The project source scope is limited to 2024")
        if self.month not in range(1, 13):
            raise ValueError("month must be between 1 and 12")

    @property
    def dataset_name(self) -> str:
        return "yellow_taxi"

    @property
    def filename(self) -> str:
        return f"yellow_tripdata_{self.year}-{self.month:02d}.parquet"

    @property
    def url(self) -> str:
        return f"{TLC_TRIP_DATA_BASE_URL}/{self.filename}"

    def destination(self, root: Path = Path("data/raw")) -> Path:
        """Return the canonical local path beneath a configurable raw root."""

        return (
            root
            / "yellow"
            / str(self.year)
            / f"{self.month:02d}"
            / self.filename
        )
