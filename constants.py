from enum import Enum


class URL(str, Enum):
    BASE = "https://digitalip.cambodiaip.gov.kh"
    SEARCH = "/api/v1/web/trademark-search"
    DETAIL = "/en/trademark-search/trademark-detail"
    IMAGE = "/trademark-detail-logo"


class SearchKey(str, Enum):
    ALL = "all"


class ImageType(str, Enum):
    DETAIL_SCREEN = "ts_logo_detail_screen"


class ScrapeMode(str, Enum):
    LIST = "list"
    ALL = "all"


MAX_RECORDS = 10
PER_PAGE = 20
ACTIVE_MODE = ScrapeMode.LIST


def build_search_payload(value: str, page: int = 1, per_page: int = PER_PAGE) -> dict:
    return {
        "data": {
            "page": str(page),
            "perPage": str(per_page),
            "search": {"key": SearchKey.ALL, "value": value},
            "filter": {
                "province": [], "country": [], "status": [],
                "applicationType": [], "markFeature": [], "classification": [],
                "date": [], "fillDate": [], "regisDate": [], "receptionDate": []
            },
            "advanceSearch": [{"type": "all", "strategy": "contains_word", "selectedValues": [], "inputValue": "", "connectingOperator": "OR"}],
            "isAdvanceSearch": "false",
            "dateOption": ""
        }
    }


FILING_NUMBERS = [
    "KH/49633/12",
    "KH/59286/14",
    "KH/83498/19",
]


JSON_FIELDS = [
    "id", 
    "number", 
    "application_date", 
    "type_of_mark", 
    "title", 
    "owner", 
    "address", 
    "status", 
    "representative"
]
