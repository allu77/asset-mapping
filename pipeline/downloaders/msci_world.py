from pipeline.download import Downloader


class MsciWorldDownloader(Downloader):
    index_id = "msci_world"
    url = (
        "https://www.ishares.com/uk/individual/en/products/251882/"
        "ishares-msci-world-ucits-etf-acc-fund/1506575576011.ajax"
        "?fileType=csv&fileName=SWDA_holdings&dataType=fund"
    )
    filename = "msci_world_raw_{date}.csv"
    prefix = "raw-csv/"
    mime_type = "text/csv"
    referer = "https://www.ishares.com/"
