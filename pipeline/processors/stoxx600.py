from pipeline.models import Holding
from pipeline.process import Processor


class Stoxx600Processor(Processor):
    index_id = "stoxx600"

    def process_row(self, row: dict[str, str]) -> Holding:
        country = self.resolve_country(row["Country"])
        return Holding(
            name=row["Asset Name"],
            country=country,
            currency=self.resolve_currency(country),
            sector=self.resolve_sector(row["Sector"]),
            weight=float(row["Weight (%)"]) / 100,
        )
