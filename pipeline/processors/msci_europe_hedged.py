from pipeline.processors.ishares import ISharesProcessor


class MsciEuropeHedgedProcessor(ISharesProcessor):
    index_id = "msci_europe_hedged"
    label = "MSCI Europe Hedged"
