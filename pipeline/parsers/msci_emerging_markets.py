from pathlib import Path

import xlrd

from pipeline.parse import Parser


class MSCIEmergingMarketsParser(Parser):
    index_id = "msci_emerging_markets"
    fields = [
        "ISIN",
    	"CUSIP",
    	"SecurityName",	
        "NumberOfShare",	
        "MarketValue",	
        "Country",	
        "LocalCurrencyCode",	
        "Weighting"
    ]

    def parse(self, src_path: Path) -> list[dict]:
        wb = xlrd.open_workbook(str(src_path))
        ws = wb.sheets()[0]
        header_row = ws.row_values(6)
        headers = [str(h) if h is not None else "" for h in header_row]
        records = []
        for i in range(7, ws.nrows):
            row = ws.row_values(i)
            d = dict(zip(headers, row))
            if not d.get("ISIN"):
                continue
            records.append({f: str(d.get(f) or "") for f in self.fields})
        return records
