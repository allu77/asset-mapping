from pipeline.models import Holding, Currency
from pipeline.process import Processor


class MSCIEmergingMarketsProcessor(Processor):
    index_id = "msci_emerging_markets"

    def filter_row(self, row: dict[str, str]) -> bool:
        return row.get("Weighting") not in [ '-', '' ]

    def process_row(self, row: dict[str, str]) -> Holding:
        return Holding(
            name=row["SecurityName"],
            country=self.resolve_country(row["Country"]),
            currency=Currency(row["LocalCurrencyCode"]),
            sector=self.resolve_sector("Unassigned"),
            weight=float(row["Weighting"]) / 100,
        )
