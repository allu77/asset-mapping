from pipeline.models import Holding, Currency
from pipeline.process import Processor


class MSCIUsaSmallCapValueWeightedProcessor(Processor):
    index_id = "msci_usa_small_cap_value_weighted"

    def filter_row(self, row: dict[str, str]) -> bool:
        return row.get("Percent of Fund") not in [ '-', '' ]

    def process_row(self, row: dict[str, str]) -> Holding:
        return Holding(
            isin=row["ISIN"],
            name=row["Security Name"],
            country=self.resolve_country(row["Trade Country Name"]),
            currency=Currency(row["Currency"]),
            sector=self.resolve_sector(row["Sector Classification"]),
            weight=float(row["Percent of Fund"]) / 100,
        )
