from pathlib import Path

import openpyxl

from pipeline.parse import Parser


class MSCIEuropeSmallCapValueWeightedParser(Parser):
    index_id = "msci_europe_small_cap_value_weighted"
    fields = [
        "ISIN",
        "SEDOL",
        "Security Name",
        "Currency",
        "Number of Shares",
        "Percent of Fund",
        "Trade Country Name",
        "Local Price",
        "Sector Classification",
        "Industry Classification",
        "Base Market Value",
    ]

    def parse(self, src_path: Path) -> list[dict]:
        wb = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(min_row=6, values_only=True)
        headers = [str(h) if h is not None else "" for h in next(rows)]
        records = []
        for row in rows:
            d = dict(zip(headers, row))
            if not d.get("ISIN"):
                continue
            records.append({f: str(d.get(f) or "") for f in self.fields})
        wb.close()
        return records
