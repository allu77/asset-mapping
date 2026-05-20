from pipeline.processors.ishares import ISharesProcessor


class MsciWorldProcessor(ISharesProcessor):
    index_id = "msci_world_enhanced_value"
    label = "MSCI World Enhanced Value"
