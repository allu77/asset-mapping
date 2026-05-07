from pipeline.models import Country, Currency, Holding, Sector
from pipeline.process import Processor


class ISharesProcessor(Processor):
    """Shared base for iShares CSV-format indices. Subclasses set min_rows, max_rows, label."""
    label: str

    def preprocess(self, content: str) -> str:
        content = content.removeprefix("﻿")  # strip UTF-8 BOM
        lines = content.splitlines()
        # Line 0: metadata ("Fund Holdings as of,..."), line 1: blank
        return "\n".join(lines[2:])

    def filter_row(self, row: dict[str, str]) -> bool:
        return row.get("Asset Class") == "Equity"

    def process_row(self, row: dict[str, str]) -> Holding:
        return Holding(
            name=row["Name"],
            isin=row.get("ISIN") or None,
            country=Country(row["Location"]),
            currency=Currency(row["Market Currency"]),
            sector=self.resolve_sector(row["Sector"]),
            weight=float(row["Weight (%)"]) / 100,
        )
