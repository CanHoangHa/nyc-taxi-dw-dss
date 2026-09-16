"""Tests for atomic, streamed TLC source downloads."""

from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

import httpx

from taxi_dw.downloader import DownloadError, download_source
from taxi_dw.source import YellowTaxiSource


class BrokenStream(httpx.SyncByteStream):
    """Yield partial content and then simulate a broken connection."""

    def __init__(self, request: httpx.Request) -> None:
        self.request = request

    def __iter__(self):
        yield b"partial"
        raise httpx.ReadError("connection interrupted", request=self.request)


class DownloaderTests(unittest.TestCase):
    def test_streams_to_final_path_and_calculates_checksum(self) -> None:
        payload = b"parquet-like-test-content"
        source = YellowTaxiSource(2024, 1)

        def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(str(request.url), source.url)
            return httpx.Response(200, content=payload)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                artifact = download_source(
                    source, root=root, client=client, chunk_size=4
                )

            self.assertEqual(artifact.path.read_bytes(), payload)
            self.assertEqual(artifact.byte_size, len(payload))
            self.assertEqual(
                artifact.sha256, hashlib.sha256(payload).hexdigest()
            )
            self.assertTrue(artifact.downloaded)
            self.assertFalse(self._part_path(source, root).exists())

    def test_reuses_completed_file_without_http_request(self) -> None:
        source = YellowTaxiSource(2024, 1)

        def unexpected_request(request: httpx.Request) -> httpx.Response:
            raise AssertionError(f"Unexpected HTTP request: {request.url}")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = source.destination(root)
            destination.parent.mkdir(parents=True)
            destination.write_bytes(b"existing")

            with httpx.Client(
                transport=httpx.MockTransport(unexpected_request)
            ) as client:
                artifact = download_source(source, root=root, client=client)

        self.assertFalse(artifact.downloaded)
        self.assertEqual(artifact.byte_size, 8)

    def test_retries_connection_error_then_succeeds(self) -> None:
        source = YellowTaxiSource(2024, 1)
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise httpx.ConnectError("temporary", request=request)
            return httpx.Response(200, content=b"complete")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                artifact = download_source(
                    source,
                    root=root,
                    client=client,
                    max_attempts=2,
                    retry_delay_seconds=0,
                )

        self.assertEqual(attempts, 2)
        self.assertTrue(artifact.downloaded)

    def test_does_not_retry_404(self) -> None:
        source = YellowTaxiSource(2024, 1)
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(404)

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(DownloadError, "HTTP 404"):
                    download_source(
                        source,
                        root=root,
                        client=client,
                        max_attempts=3,
                        retry_delay_seconds=0,
                    )

            self.assertFalse(source.destination(root).exists())
            self.assertFalse(self._part_path(source, root).exists())

        self.assertEqual(attempts, 1)

    def test_removes_partial_file_after_interrupted_stream(self) -> None:
        source = YellowTaxiSource(2024, 1)

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, stream=BrokenStream(request))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                with self.assertRaisesRegex(DownloadError, "interrupted"):
                    download_source(
                        source,
                        root=root,
                        client=client,
                        max_attempts=1,
                        retry_delay_seconds=0,
                    )

            self.assertFalse(source.destination(root).exists())
            self.assertFalse(self._part_path(source, root).exists())

    @staticmethod
    def _part_path(source: YellowTaxiSource, root: Path) -> Path:
        destination = source.destination(root)
        return destination.with_name(f"{destination.name}.part")


if __name__ == "__main__":
    unittest.main()
