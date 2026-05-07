from pipeline.processors.ishares import ISharesProcessor


class MsciWorldProcessor(ISharesProcessor):
    index_id = "msci_world"
    label = "MSCI World"
