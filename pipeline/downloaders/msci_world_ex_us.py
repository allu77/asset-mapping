from pipeline.download import Downloader


class MSCIWorldExUsDownloader(Downloader):
    index_id = "msci_world_ex_us"
    url = "https://etf.dws.com/etfdata/export/ITA/ITA/excel/product/constituent/IE0006WW1TQ4/"
    filename = "msci_world_ex_us_raw_{date}.xlsx"
    prefix = "xls/"
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    referer = "https://etf.dws.com/"
