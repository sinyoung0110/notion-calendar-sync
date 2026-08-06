from notion_client import Client
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import json
# =====================
# Notion
# =====================


NOTION_TOKEN = os.environ["NOTION_TOKEN"]

notion = Client(auth=NOTION_TOKEN)

data_source_id = "e4f96717-d484-82a5-8212-0719c35b885a"

# =====================
# Google Calendar 설정
# =====================

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]

google_token = os.environ["GOOGLE_TOKEN"]

creds = Credentials.from_authorized_user_info(
    json.loads(google_token),
    SCOPES
)

calendar = build(
    "calendar",
    "v3",
    credentials=creds
)


# =====================
# Notion 전체 조회
# =====================

results = notion.data_sources.query(
    data_source_id=data_source_id
)


count_create = 0
count_update = 0


for page in results["results"]:

    props = page["properties"]


    # 제목
    title_data = props["ToDo"]["title"]

    if not title_data:
        continue

    title = title_data[0]["plain_text"]


    # 시간 확인
    formula = props["시작~종료"]["formula"]["date"]

    if not formula:
        print("시간 없음:", title)
        continue


    start = formula["start"]
    end = formula["end"]


    # Google Event ID 확인
    event_id_data = props["Google Event ID"]["rich_text"]


    # =====================
    # 이미 있으면 수정
    # =====================

    if event_id_data:

        event_id = event_id_data[0]["text"]["content"]

        print("수정:", title)

        event = {
            "summary": title,
            "start": {
                "dateTime": start,
                "timeZone": "Asia/Seoul"
            },
            "end": {
                "dateTime": end,
                "timeZone": "Asia/Seoul"
            }
        }


        calendar.events().update(
            calendarId="primary",
            eventId=event_id,
            body=event
        ).execute()


        count_update += 1


    # =====================
    # 없으면 생성
    # =====================

    else:

        print("생성:", title)

        event = {
            "summary": title,
            "start": {
                "dateTime": start,
                "timeZone": "Asia/Seoul"
            },
            "end": {
                "dateTime": end,
                "timeZone": "Asia/Seoul"
            }
        }


        created = calendar.events().insert(
            calendarId="primary",
            body=event
        ).execute()


        event_id = created["id"]


        # Notion에 ID 저장
        notion.pages.update(
            page_id=page["id"],
            properties={
                "Google Event ID": {
                    "rich_text": [
                        {
                            "text": {
                                "content": event_id
                            }
                        }
                    ]
                }
            }
        )


        print("ID 저장:", event_id)

        count_create += 1



print("\n================")
print("생성:", count_create)
print("수정:", count_update)
print("================")