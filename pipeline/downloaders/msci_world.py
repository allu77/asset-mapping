from pipeline.download import Downloader


class MsciWorldDownloader(Downloader):
    index_id = "msci_world"
    # iShares rebuilt their site: the old ".ajax?fileType=csv" path now returns the SPA
    # HTML page. This BlackRock product-data endpoint with component=holdings returns the
    # same classic holdings CSV (the "Detailed Holdings and Analytics" download).
    url = (
        "https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v1/"
        "get-fund-document"
        "?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=ishares-uk&locale=en_GB"
        "&portfolioId=251882&component=holdings&userType=individual"
    )
    filename = "msci_world_raw_{date}.csv"
    prefix = "raw-csv/"
    mime_type = "text/csv"
    referer = "https://www.ishares.com/"
