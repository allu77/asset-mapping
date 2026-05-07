from pipeline.download import Downloader


class MsciEuropeHedgedDownloader(Downloader):
    index_id = "msci_europe_hedged"
    url = (
        "https://www.ishares.com/uk/individual/en/products/311870/"
        "fund/1506575576011.ajax"
        "?fileType=csv&fileName=IMEAX_holdings&dataType=fund"
    )
    filename = "msci_europe_hedged_raw_{date}.csv"
    prefix = "raw-csv/"
    mime_type = "text/csv"
    referer = "https://www.ishares.com/"
