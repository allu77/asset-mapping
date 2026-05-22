import csv
import io
import json
from urllib.parse import quote

from google.auth.transport.requests import AuthorizedSession
from google.oauth2 import service_account

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def upload(csv_content: str, credentials_json: str, sheet_id: str, sheet_name: str) -> dict:
    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json), scopes=_SCOPES
    )
    session = AuthorizedSession(creds)
    rows = list(csv.reader(io.StringIO(csv_content)))

    r_clear = quote(f"{sheet_name}!A:F", safe="")
    r_update = quote(f"{sheet_name}!A1", safe="")

    session.post(f"{_BASE}/{sheet_id}/values/{r_clear}:clear").raise_for_status()
    session.put(
        f"{_BASE}/{sheet_id}/values/{r_update}",
        params={"valueInputOption": "USER_ENTERED"},
        json={"values": rows},
    ).raise_for_status()

    return {"sheet_id": sheet_id, "rows_written": len(rows)}
