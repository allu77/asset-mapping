from pipeline.models import Holding, Currency
from pipeline.process import Processor


class MSCIWorldExUsProcessor(Processor):
    index_id = "msci_world_ex_us"

    def filter_row(self, row: dict[str, str]) -> bool:
        return row.get("Type of Security") == "Azionari"

    def process_row(self, row: dict[str, str]) -> Holding:
        return Holding(
            isin=row["ISIN"],
            name=row["Name"],
            country=self.resolve_country(row["Country"]),
            currency=Currency(row["Currency"]),
            sector=self.resolve_sector(row["Industry Classification"]),
            weight=float(row["Weighting"]),
        )
