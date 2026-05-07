from pipeline.download import Downloader


class Stoxx600Downloader(Downloader):
    index_id = "stoxx600"
    url = "https://www.stoxx.com/document/Bookmarks/CurrentComponents/SXXGV.pdf"
    filename = "stoxx600_raw_{date}.pdf"
    prefix = "pdf/"
    mime_type = "application/pdf"
    referer = "https://www.stoxx.com/"
