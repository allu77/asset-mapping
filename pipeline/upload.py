import csv
import io
import json

from google.oauth2 import service_account
from googleapiclient.discovery import build

_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def upload(csv_content: str, credentials_json: str, sheet_id: str, sheet_name: str) -> dict:
    creds = service_account.Credentials.from_service_account_info(
        json.loads(credentials_json), scopes=_SCOPES
    )
    spreadsheets = build("sheets", "v4", credentials=creds).spreadsheets()

    rows = list(csv.reader(io.StringIO(csv_content)))

    spreadsheets.values().clear(spreadsheetId=sheet_id, range=f"{sheet_name}!A:F").execute()
    spreadsheets.values().update(
        spreadsheetId=sheet_id,
        range=f"{sheet_name}!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()

    return {"sheet_id": sheet_id, "rows_written": len(rows)}
