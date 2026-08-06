from notion_client import Client
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import os
import json


# =====================
# Notion 설정
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
# 과목별 색상 설정
# =====================

SUBJECT_COLOR = {
    "국어": "9",          # 파랑/하늘색
    "영어": "4",          # 분홍/빨강
    "일반 컴퓨터": "5",   # 노랑
    "정보보호론": "10"    # 초록
}


# =====================
# 과목 가져오기 함수
# =====================

def get_subject(props):

    try:
        rollup = props["과목"]["rollup"]

        if rollup["type"] != "array":
            return None

        array = rollup["array"]

        if not array:
            return None

        first = array[0]

        # Relation으로 연결된 페이지 제목
        if "title" in first:
            return first["title"][0]["plain_text"]

    except Exception:
        pass

    return None



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


    # =====================
    # 제목
    # =====================

    title_data = props["ToDo"]["title"]

    if not title_data:
        continue

    title = title_data[0]["plain_text"]



    # =====================
    # 과목 색상
    # =====================

    subject = get_subject(props)

    color_id = SUBJECT_COLOR.get(
        subject,
        "1"
    )

    print("과목:", subject, "색상:", color_id)



    # =====================
    # 시간 확인
    # =====================

    formula_date = props["시작~종료"]["formula"]["date"]

    if not formula_date:
        print("시간 없음:", title)
        continue


    start = formula_date["start"]
    end = formula_date["end"]



    # =====================
    # Google Event ID 확인
    # =====================

    event_id_data = props["Google Event ID"]["rich_text"]



    event = {
        "summary": title,
        "colorId": color_id,
        "start": {
            "dateTime": start,
            "timeZone": "Asia/Seoul"
        },
        "end": {
            "dateTime": end,
            "timeZone": "Asia/Seoul"
        }
    }



    # =====================
    # 기존 일정 수정
    # =====================

    if event_id_data:

        event_id = event_id_data[0]["plain_text"]

        print("수정:", title)

        calendar.events().update(
            calendarId="primary",
            eventId=event_id,
            body=event
        ).execute()


        count_update += 1



    # =====================
    # 신규 생성
    # =====================

    else:

        print("생성:", title)


        created = calendar.events().insert(
            calendarId="primary",
            body=event
        ).execute()


        event_id = created["id"]


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