"""Stream monthly TLC source files to their canonical local paths."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time

import httpx

from taxi_dw.source import YellowTaxiSource


DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=60, write=60, pool=10)


class DownloadError(RuntimeError):
    """Raised when a source cannot be downloaded safely."""


@dataclass(frozen=True, slots=True)
class DownloadedArtifact:
    """Facts needed by the next validation and audit milestones."""

    source: YellowTaxiSource
    path: Path
    byte_size: int
    sha256: str
    downloaded: bool
    observed_at: datetime


def download_source(
    source: YellowTaxiSource,
    *,
    root: Path = Path("data/raw"),
    client: httpx.Client | None = None,
    max_attempts: int = 3,
    retry_delay_seconds: float = 1.0,
    chunk_size: int = 1024 * 1024,
) -> DownloadedArtifact:
    """Download a source atomically, or reuse an existing completed file."""

    if max_attempts < 1 or chunk_size < 1 or retry_delay_seconds < 0:
        raise ValueError("invalid download retry or chunk configuration")

    destination = source.destination(root)
    if destination.exists():
        if destination.stat().st_size == 0:
            raise DownloadError(f"Existing source file is empty: {destination}")
        return _artifact(source, destination, downloaded=False)

    destination.parent.mkdir(parents=True, exist_ok=True)
    part_path = destination.with_name(f"{destination.name}.part")

    if client is not None:
        return _download_with_retries(
            source,
            destination,
            part_path,
            client,
            max_attempts,
            retry_delay_seconds,
            chunk_size,
        )

    with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as owned_client:
        return _download_with_retries(
            source,
            destination,
            part_path,
            owned_client,
            max_attempts,
            retry_delay_seconds,
            chunk_size,
        )


def calculate_sha256(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Calculate a file checksum without loading the whole artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as source_file:
        for chunk in iter(lambda: source_file.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _download_with_retries(
    source: YellowTaxiSource,
    destination: Path,
    part_path: Path,
    client: httpx.Client,
    max_attempts: int,
    retry_delay_seconds: float,
    chunk_size: int,
) -> DownloadedArtifact:
    for attempt in range(1, max_attempts + 1):
        part_path.unlink(missing_ok=True)
        try:
            return _download_once(
                source, destination, part_path, client, chunk_size
            )
        except (httpx.RequestError, httpx.HTTPStatusError) as error:
            if attempt == max_attempts or not _retryable(error):
                part_path.unlink(missing_ok=True)
                raise DownloadError(_error_message(source, error)) from error
            if retry_delay_seconds:
                time.sleep(retry_delay_seconds * attempt)

    raise AssertionError("download retry loop ended unexpectedly")


def _download_once(
    source: YellowTaxiSource,
    destination: Path,
    part_path: Path,
    client: httpx.Client,
    chunk_size: int,
) -> DownloadedArtifact:
    digest = hashlib.sha256()
    bytes_written = 0
    try:
        with client.stream("GET", source.url) as response:
            response.raise_for_status()
            expected_size = _content_length(response)
            with part_path.open("wb") as output_file:
                for chunk in response.iter_bytes(chunk_size):
                    output_file.write(chunk)
                    digest.update(chunk)
                    bytes_written += len(chunk)

            if bytes_written == 0:
                raise httpx.ReadError(
                    "source response was empty", request=response.request
                )
            if expected_size is not None and bytes_written != expected_size:
                raise httpx.ReadError(
                    f"expected {expected_size} bytes but received {bytes_written}",
                    request=response.request,
                )

        part_path.replace(destination)
    except Exception:
        part_path.unlink(missing_ok=True)
        raise

    return DownloadedArtifact(
        source=source,
        path=destination.resolve(),
        byte_size=bytes_written,
        sha256=digest.hexdigest(),
        downloaded=True,
        observed_at=datetime.now(timezone.utc),
    )


def _content_length(response: httpx.Response) -> int | None:
    if response.headers.get("content-encoding"):
        return None
    value = response.headers.get("content-length")
    return int(value) if value and value.isdigit() else None


def _retryable(error: httpx.RequestError | httpx.HTTPStatusError) -> bool:
    if isinstance(error, httpx.RequestError):
        return True
    return error.response.status_code == 429 or error.response.status_code >= 500


def _error_message(
    source: YellowTaxiSource,
    error: httpx.RequestError | httpx.HTTPStatusError,
) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return (
            f"Download failed for {source.filename}: "
            f"HTTP {error.response.status_code}"
        )
    return f"Download failed for {source.filename}: {error}"


def _artifact(
    source: YellowTaxiSource, path: Path, *, downloaded: bool
) -> DownloadedArtifact:
    return DownloadedArtifact(
        source=source,
        path=path.resolve(),
        byte_size=path.stat().st_size,
        sha256=calculate_sha256(path),
        downloaded=downloaded,
        observed_at=datetime.now(timezone.utc),
    )


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--month", type=int, required=True)
    parser.add_argument("--root", type=Path, default=Path("data/raw"))
    options = parser.parse_args(arguments)

    artifact = download_source(
        YellowTaxiSource(options.year, options.month), root=options.root
    )
    action = "downloaded" if artifact.downloaded else "reused"
    print(
        f"{action}: {artifact.path} "
        f"({artifact.byte_size:,} bytes, sha256={artifact.sha256})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
