"""Validated TOML configuration for reproducible DSS experiments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 only
    import tomli as tomllib

from dss.contracts import ContractError
from dss.split import TemporalSplit


@dataclass(frozen=True)
class ModelSettings:
    max_iter: int = 100
    learning_rate: float = 0.08
    max_leaf_nodes: int = 31
    random_state: int = 42


@dataclass(frozen=True)
class DssConfig:
    dataset_start: date
    dataset_end: date
    split: TemporalSplit
    model: ModelSettings
    artifact_directory: Path

    def validate(self) -> None:
        self.split.validate()
        if self.dataset_start > self.dataset_end:
            raise ContractError("dataset start must not be after dataset end")
        if self.dataset_start > self.split.train_start or self.dataset_end < self.split.test_end:
            raise ContractError("dataset bounds must contain all temporal splits")
        if self.model.max_iter < 1 or self.model.max_leaf_nodes < 2:
            raise ContractError("model iteration and leaf settings must be positive")
        if not 0 < self.model.learning_rate <= 1:
            raise ContractError("model learning_rate must be within (0, 1]")


def load_config(path: Path) -> DssConfig:
    """Load a DSS config without accepting unknown implicit date formats."""

    with Path(path).open("rb") as handle:
        raw = tomllib.load(handle)
    try:
        dataset = raw["dataset"]
        split = raw["split"]
        model = raw.get("model", {})
        artifacts = raw["artifacts"]
        config = DssConfig(
            dataset_start=_date(dataset["start_date"], "dataset.start_date"),
            dataset_end=_date(dataset["end_date"], "dataset.end_date"),
            split=TemporalSplit(
                train_start=_date(split["train_start"], "split.train_start"),
                train_end=_date(split["train_end"], "split.train_end"),
                validation_start=_date(
                    split["validation_start"], "split.validation_start"
                ),
                validation_end=_date(split["validation_end"], "split.validation_end"),
                test_start=_date(split["test_start"], "split.test_start"),
                test_end=_date(split["test_end"], "split.test_end"),
            ),
            model=ModelSettings(
                max_iter=int(model.get("max_iter", 100)),
                learning_rate=float(model.get("learning_rate", 0.08)),
                max_leaf_nodes=int(model.get("max_leaf_nodes", 31)),
                random_state=int(model.get("random_state", 42)),
            ),
            artifact_directory=Path(artifacts["directory"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ContractError(f"invalid DSS config: {error}") from error
    config.validate()
    return config


def config_as_dict(config: DssConfig) -> dict[str, Any]:
    return {
        "dataset_start": config.dataset_start.isoformat(),
        "dataset_end": config.dataset_end.isoformat(),
        "split": {
            field: getattr(config.split, field).isoformat()
            for field in config.split.__dataclass_fields__
        },
        "model": {
            field: getattr(config.model, field)
            for field in config.model.__dataclass_fields__
        },
    }


def _date(value: object, label: str) -> date:
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ContractError(f"{label} must be an ISO date") from error
