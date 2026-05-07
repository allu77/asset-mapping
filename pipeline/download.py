from dataclasses import dataclass
from datetime import date

import requests

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_registry: dict[str, type["Downloader"]] = {}


@dataclass
class DownloadResult:
    content: bytes
    key: str       # full storage key, e.g. "raw-csv/IWDA_2026-05-01.csv"
    mime_type: str


class Downloader:
    index_id: str
    url: str
    filename: str   # supports {date} placeholder
    prefix: str     # storage folder, e.g. "pdf/" or "raw-csv/"
    mime_type: str
    referer: str

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "index_id") and cls.index_id:
            _registry[cls.index_id] = cls

    @classmethod
    def create(cls, index_id: str) -> "Downloader":
        if index_id not in _registry:
            raise ValueError(f"Unknown index '{index_id}'. Available: {list(_registry)}")
        return _registry[index_id]()

    @classmethod
    def index_ids(cls) -> list[str]:
        return list(_registry)

    def download(self) -> DownloadResult:
        today = date.today().isoformat()
        resp = requests.get(
            self.url,
            headers={"User-Agent": _UA, "Accept": "*/*", "Referer": self.referer},
            timeout=30,
        )
        if resp.status_code == 403:
            raise RuntimeError(
                f"[{self.index_id}] Source returned 403 — download blocked. "
                "Consider routing via a fixed Elastic IP."
            )
        resp.raise_for_status()
        if len(resp.content) < 10_000:
            raise RuntimeError(
                f"[{self.index_id}] Response too small ({len(resp.content)} bytes) — "
                "source may have changed or returned an error page."
            )
        key = f"{self.prefix}{self.filename.format(date=today)}"
        return DownloadResult(content=resp.content, key=key, mime_type=self.mime_type)


# Auto-import every module in pipeline/downloaders/ to populate the registry.
# Adding a new downloader only requires a new file there — no changes here.
import importlib
import pkgutil
import pipeline.downloaders as _downloaders_pkg

for _mod in pkgutil.iter_modules(_downloaders_pkg.__path__):
    importlib.import_module(f"pipeline.downloaders.{_mod.name}")


def download(index_id: str) -> DownloadResult:
    return Downloader.create(index_id).download()
