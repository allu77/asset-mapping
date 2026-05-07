import re
from pathlib import Path

import pypdf

from pipeline.parse import Parser

SUPERSECTORS = {
    "Food, Beverage & Tobacco",
    "Technology",
    "Health Care",
    "Consumer Products & Services",
    "Energy",
    "Banks",
    "Personal Care, Drug & Grocery Stores",
    "Industrial Goods & Services",
    "Chemicals",
    "Insurance",
    "Utilities",
    "Telecommunications",
    "Basic Resources",
    "Financial Services",
    "Media",
    "Automobiles & Parts",
    "Retail",
    "Construction & Materials",
    "Travel & Leisure",
    "Real Estate",
}

COUNTRIES = {
    "Switzerland", "Netherlands", "Denmark", "France", "Great Britain",
    "Germany", "Spain", "Italy", "Sweden", "Finland", "Norway", "Belgium",
    "Ireland", "Austria", "Portugal", "Luxembourg", "Poland",
}


class Stoxx600Parser(Parser):
    index_id = "stoxx600"
    fields = ["Asset Name", "Sector", "Country", "Weight (%)"]

    def parse(self, src_path: Path) -> list[dict]:
        reader = pypdf.PdfReader(src_path)
        full_text = "\n".join(page.extract_text() or "" for page in reader.pages)

        sorted_supersectors = sorted(SUPERSECTORS, key=len, reverse=True)
        sorted_countries    = sorted(COUNTRIES,    key=len, reverse=True)
        ss_pattern  = "|".join(re.escape(s) for s in sorted_supersectors)
        cty_pattern = "|".join(re.escape(c) for c in sorted_countries)

        line_re = re.compile(
            rf"^(.+?)\s+({ss_pattern})\s+({cty_pattern})\s+([\d.]+)\s*$"
        )
        weight_re = re.compile(r"\d\d?\.\d\d$")

        records = []
        seen = set()
        suspect_lines = []

        for raw_line in full_text.splitlines():
            line = raw_line.strip()
            m = line_re.match(line)
            if not m:
                if weight_re.search(line):
                    suspect_lines.append(line)
                continue

            company     = m.group(1).strip()
            supersector = m.group(2).strip()
            country     = m.group(3).strip()
            weight      = float(m.group(4))

            if company.lower() in {"company", "components1", "components"}:
                continue

            key = (company, supersector, country)
            if key in seen:
                continue
            seen.add(key)

            records.append({
                "Asset Name": company,
                "Sector":     supersector,
                "Country":    country,
                "Weight (%)": weight,
            })

        if len(records) != 600:
            detail = f"suspect lines: {suspect_lines[:5]}" if suspect_lines else "no suspect lines"
            raise ValueError(
                f"Expected 600 constituents but parsed {len(records)}. "
                f"PDF layout may have changed ({detail})."
            )

        return records
