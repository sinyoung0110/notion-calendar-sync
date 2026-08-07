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
#
# 기존 코드는 롤업 배열의 첫 항목이 항상 "title" 타입이라고
# 가정하고 있었는데, 실제 관련 DB의 "과목" 속성이 select나
# rich_text 등 다른 타입이면 이 조건에 걸리지 않아서 항상 None을
# 반환하고, 결과적으로 색상이 항상 기본값("1")으로만 적용됐을
# 가능성이 큽니다.
#
# 아래처럼 실제 타입(title / select / rich_text)을 모두 처리하도록
# 수정했고, 에러도 조용히 삼키지 않고 로그에 남기도록 했습니다.
# 만약 이래도 색상이 안 먹으면, 아래 DEBUG 프린트로 실제 구조를
# 확인해서 타입을 하나 더 추가해주면 됩니다.

def get_subject(props):

    try:
        rollup = props["과목"]["rollup"]

        if rollup["type"] != "array":
            return None

        array = rollup["array"]

        if not array:
            return None

        first = array[0]

        item_type = first.get("type")

        if item_type == "title":
            title_list = first.get("title") or []
            if title_list:
                return title_list[0]["plain_text"]

        elif item_type == "select":
            select_value = first.get("select")
            if select_value:
                return select_value["name"]

        elif item_type == "rich_text":
            rich_text_list = first.get("rich_text") or []
            if rich_text_list:
                return rich_text_list[0]["plain_text"]

        else:
            print("get_subject: 처리하지 않은 rollup item type:", item_type)

    except Exception as e:
        print("get_subject error:", e)

    return None



# =====================
# Notion 전체 조회
# =====================

results = notion.data_sources.query(
    data_source_id=data_source_id
)


count_create = 0
count_update = 0
count_skip = 0


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

    # 디버그가 필요하면 아래 주석을 풀어서 "과목" 속성의
    # 실제 JSON 구조를 로그로 확인할 수 있습니다.
    # print("DEBUG 과목 raw:", json.dumps(props.get("과목"), ensure_ascii=False))

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
        count_skip += 1
        continue


    start = formula_date.get("start")
    end = formula_date.get("end")

    # 시작 시간만 있고 종료 시간이 없는 경우(단일 날짜 등)도
    # Google Calendar API는 end.dateTime을 요구하기 때문에
    # 여기서 같이 걸러줘야 합니다. 그냥 무시하고 넘어가는 게
    # 맞다면 이대로, 종료 시간을 자동으로 채우고 싶다면 이
    # 아래에서 end = start 등으로 보정해도 됩니다.
    if not start or not end:
        print("시작/종료 시간 불완전:", title)
        count_skip += 1
        continue



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
print("건너뜀(시간 없음):", count_skip)
print("================")