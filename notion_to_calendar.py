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
    "국어": "7",          # Peacock - 하늘색
    "영어": "4",          # Flamingo - 분홍색
    "한국사": "1",
    "일반 컴퓨터": "5",   # Banana - 노란색
    "정보보호론": "2"    # Basil - 초록색
}

DEFAULT_COLOR = "8"  # Graphite - 회색 (기타/매칭 안 되는 과목)


# =====================
# 과목 가져오기 함수
# =====================
#
# "과목" 속성이 롤업(rollup)일 수도 있고, 관련 DB 구조에 따라
# select / multi_select / rich_text / title 속성 자체일 수도
# 있어서, 속성의 실제 type을 먼저 확인한 뒤 그에 맞게 값을
# 꺼내오도록 만들었습니다. 이렇게 하면 "과목"이 어떤 형태로
# 설정돼 있어도 대부분 잡아낼 수 있습니다.
#
# 에러도 조용히 삼키지 않고 로그에 남기도록 했으니, 그래도 색이
# 안 먹으면 Actions 로그에서 "get_subject" 관련 출력을 확인해
# 주세요.
# =====================
# 과목 가져오기 함수 (relation 직접 조회 방식)
# =====================
#
# 롤업 값은 Notion 쪽에서 API 반영이 지연되는 경우가 있어서,
# 롤업 대신 "프로젝트 이름" relation을 직접 따라가 연결된
# 프로젝트 페이지를 조회하고, 거기서 "과목" select 값을
# 바로 가져오도록 변경했습니다.

def get_subject(props):

    try:
        relation_prop = props.get("프로젝트 이름")

        if not relation_prop or relation_prop.get("type") != "relation":
            print("get_subject: '프로젝트 이름' relation을 찾을 수 없음")
            return None

        relation_list = relation_prop.get("relation") or []

        if not relation_list:
            print("get_subject: 연결된 프로젝트 없음")
            return None

        project_page_id = relation_list[0]["id"]

        # 연결된 프로젝트 페이지를 직접 조회해서 "과목" select 값을 가져옴
        project_page = notion.pages.retrieve(page_id=project_page_id)

        subject_prop = project_page["properties"].get("과목")

        if not subject_prop or subject_prop.get("type") != "select":
            print("get_subject: 프로젝트 페이지에 '과목' select 없음")
            return None

        select_value = subject_prop.get("select")

        return select_value["name"] if select_value else None

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

    # 앞뒤 공백 차이로 매칭이 안 되는 경우를 막기 위해 strip 처리
    if subject:
        subject = subject.strip()

    # 디버그가 필요하면 아래 주석을 풀어서 "과목" 속성의
    # 실제 JSON 구조를 로그로 확인할 수 있습니다.
    print("DEBUG 과목 raw:", json.dumps(props.get("과목"), ensure_ascii=False))

    color_id = SUBJECT_COLOR.get(
        subject,
        DEFAULT_COLOR
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