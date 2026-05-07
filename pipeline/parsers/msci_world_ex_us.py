from pathlib import Path

import openpyxl

from pipeline.parse import Parser


class MsciWorldExUsParser(Parser):
    index_id = "msci_world_ex_us"
    fields = [
        "Name",
        "ISIN",
        "Country",
        "Currency",
        "Type of Security",
        "Industry Classification",
        "Weighting",
    ]

    def parse(self, src_path: Path) -> list[dict]:
        wb = openpyxl.load_workbook(src_path, read_only=True, data_only=True)
        ws = wb.active
        rows = ws.iter_rows(min_row=4, values_only=True)
        headers = [str(h) if h is not None else "" for h in next(rows)]
        records = []
        for row in rows:
            d = dict(zip(headers, row))
            if not d.get("Name"):
                continue
            records.append({f: str(d.get(f) or "") for f in self.fields})
        wb.close()
        if not (700 <= len(records) <= 1200):
            raise ValueError(
                f"[{self.index_id}] Expected 700–1200 records, got {len(records)}."
            )
        return records
