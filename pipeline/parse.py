import csv
import importlib
import io
import pkgutil
from abc import ABC, abstractmethod
from pathlib import Path

_registry: dict[str, type["Parser"]] = {}


class Parser(ABC):
    index_id: str
    fields: list[str]  # raw-csv column order (may differ per index)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "index_id") and cls.index_id:
            _registry[cls.index_id] = cls

    @classmethod
    def create(cls, index_id: str) -> "Parser":
        if index_id not in _registry:
            raise ValueError(f"Unknown index '{index_id}'. Available: {list(_registry)}")
        return _registry[index_id]()

    @classmethod
    def index_ids(cls) -> list[str]:
        return list(_registry)

    @abstractmethod
    def parse(self, src_path: Path) -> list[dict]:
        ...

    def to_csv(self, records: list[dict]) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=self.fields)
        writer.writeheader()
        writer.writerows(records)
        return buf.getvalue()


# Auto-import every module in pipeline/parsers/ to populate the registry.
# Adding a new parser only requires a new file there — no changes here.
import pipeline.parsers as _parsers_pkg

for _mod in pkgutil.iter_modules(_parsers_pkg.__path__):
    importlib.import_module(f"pipeline.parsers.{_mod.name}")
