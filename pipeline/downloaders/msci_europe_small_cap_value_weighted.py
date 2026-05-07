from pipeline.download import Downloader


class MSCIEuropsSmallCapValueWeightedDownloader(Downloader):
    index_id = "msci_europe_small_cap_value_weighted"
    url = "https://www.ssga.com/it/it/intermediary/library-content/products/fund-data/etfs/emea/holdings-daily-emea-en-zprx-gy.xlsx"
    filename = "msci_europe_small_cap_value_weighted_raw_{date}.xlsx"
    prefix = "xls/"
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    referer = "https://www.ssga.com/"
