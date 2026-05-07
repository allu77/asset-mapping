import csv
import importlib
import io
import pkgutil
from abc import ABC, abstractmethod

from pipeline.models import Country, Currency, Holding, Sector
from pipeline import mappings

_registry: dict[str, type["Processor"]] = {}

_OUTPUT_FIELDS = ["Asset Name", "ISIN", "Country", "Currency", "Sector", "Weight (%)"]


class Processor(ABC):
    index_id: str
    min_weight_sum: float = 0.98
    max_weight_sum: float = 1.01

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "index_id") and cls.index_id:
            _registry[cls.index_id] = cls

    @classmethod
    def create(cls, index_id: str) -> "Processor":
        if index_id not in _registry:
            raise ValueError(f"Unknown index '{index_id}'. Available: {list(_registry)}")
        return _registry[index_id]()

    @classmethod
    def index_ids(cls) -> list[str]:
        return list(_registry)

    def resolve_country(self, raw: str) -> Country:
        return mappings.resolve_country(raw)

    def resolve_currency(self, country: Country) -> Currency:
        return mappings.resolve_currency(country)

    def resolve_sector(self, raw: str) -> Sector:
        return mappings.resolve_sector(raw)

    def preprocess(self, content: str) -> str:
        """Override to clean/transform raw content before CSV parsing."""
        return content

    def filter_row(self, row: dict[str, str]) -> bool:
        """Override to skip unwanted rows (e.g. non-equity asset classes)."""
        return True

    def validate(self, holdings: list[Holding]) -> None:
        """Override to add extra invariants; always call super() to retain weight-sum check."""
        total = sum(h.weight for h in holdings)
        if not (self.min_weight_sum <= total <= self.max_weight_sum):
            raise ValueError(
                f"[{self.index_id}] Weight sum {total:.4f} outside expected range "
                f"[{self.min_weight_sum}, {self.max_weight_sum}]."
            )

    @abstractmethod
    def process_row(self, row: dict[str, str]) -> Holding:
        """Map one CSV row to a canonical Holding."""
        ...

    def process(self, content: str) -> list[Holding]:
        content = self.preprocess(content)
        holdings = [
            self.process_row(row)
            for row in csv.DictReader(io.StringIO(content))
            if self.filter_row(row)
        ]
        self.validate(holdings)
        return holdings

    def to_csv(self, holdings: list[Holding]) -> str:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_OUTPUT_FIELDS)
        writer.writeheader()
        for h in holdings:
            writer.writerow({
                "Asset Name": h.name,
                "ISIN":       h.isin or "",
                "Currency":   h.currency.value,
                "Sector":     h.sector.value,
                "Weight (%)": round(h.weight, 4),
                "Country":    h.country.value,
            })
        return buf.getvalue()


# Auto-import every module in pipeline/processors/ to populate the registry.
# Adding a new processor only requires a new file there — no changes here.
import pipeline.processors as _processors_pkg

for _mod in pkgutil.iter_modules(_processors_pkg.__path__):
    importlib.import_module(f"pipeline.processors.{_mod.name}")
