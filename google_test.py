from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import datetime
import os


SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]


def get_calendar_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(
            "client_secret.json",
            SCOPES
        )

        creds = flow.run_local_server(
            port=0
        )

        with open("token.json", "w") as token:
            token.write(creds.to_json())

    service = build(
        "calendar",
        "v3",
        credentials=creds
    )

    return service


service = get_calendar_service()


event = {
    "summary": "Notion API 테스트 일정",
    "description": "노션 → 구글 캘린더 연결 테스트",
    "start": {
        "dateTime": "2026-08-07T15:00:00+09:00",
        "timeZone": "Asia/Seoul",
    },
    "end": {
        "dateTime": "2026-08-07T16:00:00+09:00",
        "timeZone": "Asia/Seoul",
    },
}


result = service.events().insert(
    calendarId="primary",
    body=event
).execute()


print("생성 완료")
print(result["htmlLink"])