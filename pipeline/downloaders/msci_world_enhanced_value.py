from pipeline.download import Downloader


class MsciWorldEnhancedValue(Downloader):
    index_id = "msci_world_enhanced_value"
    url = (
        "https://www.ishares.com/uk/individual/en/products/270048/"
        "ishares-msci-world-value-factor-ucits-etf/1506575576011.ajax"
        "?fileType=csv&fileName=IWVL_holdings&dataType=fund"
    )
    filename = "msci_world_enhanced_value_raw_{date}.csv"
    prefix = "raw-csv/"
    mime_type = "text/csv"
    referer = "https://www.ishares.com/"

