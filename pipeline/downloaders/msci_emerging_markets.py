from pipeline.download import Downloader


class MSCIEmergingMarketsDownloader(Downloader):
    index_id = "msci_emerging_markets"
    url = "https://www.assetmanagement.hsbc.it/it/api/v1/download/document/ie000kcs7j59/it/it/holdings"
    filename = "msci_emerging_markets_raw_{date}.xls"
    prefix = "xls/"
    mime_type = " application/vnd.ms-excel"
    referer = "www.assetmanagement.hsbc.it/"
