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
    "정보보호론": "2"     # Basil - 초록색
}

DEFAULT_COLOR = "8"  # Graphite - 회색 (기타/매칭 안 되는 과목)


# 프로젝트 페이지를 반복해서 다시 조회하지 않도록 캐싱
# (같은 프로젝트에 연결된 ToDo가 여러 개면 API 호출을 아낄 수 있음)
_project_subject_cache = {}


# =====================
# 과목 가져오기 함수 (relation 직접 조회 방식)
# =====================
#
# "과목" 롤업 값은 Notion 쪽에서 API 반영이 지연되는 경우가 있어서
# (relation을 새로 연결한 직후 롤업 캐시가 늦게 갱신되는 케이스),
# 롤업을 거치지 않고 "프로젝트 이름" relation을 직접 따라가
# 연결된 프로젝트 페이지를 조회한 뒤, 그 페이지의 "과목" select
# 값을 바로 읽어오는 방식으로 변경했습니다.
#
# 이렇게 하면 항상 최신 값을 가져오고, Notion DB 구조를 새로
# 만들 필요 없이 기존 "프로젝트 이름" relation만 그대로 씁니다.

def get_subject(props):

    try:
        # 디버그: "프로젝트 이름" 속성의 실제 원본 구조 확인
        print("DEBUG 프로젝트 이름 raw:", json.dumps(props.get("프로젝트 이름"), ensure_ascii=False))
        title = title_data[0]["plain_text"]

        print("DEBUG 페이지 URL:", page.get("url"))
        print("DEBUG 페이지 ID:", page.get("id"))

        relation_prop = props.get("프로젝트 이름")

        if not relation_prop or relation_prop.get("type") != "relation":
            print("get_subject: '프로젝트 이름' relation 속성을 찾을 수 없음")
            return None

        relation_list = relation_prop.get("relation") or []

        if not relation_list:
            print("get_subject: 연결된 프로젝트 없음")
            return None

        # 여러 프로젝트가 연결돼 있어도 첫 번째 것만 사용
        project_page_id = relation_list[0]["id"]

        # 같은 프로젝트를 이미 조회했다면 캐시에서 바로 반환
        if project_page_id in _project_subject_cache:
            return _project_subject_cache[project_page_id]

        # 연결된 프로젝트 페이지를 직접 조회해서 "과목" select 값을 가져옴
        project_page = notion.pages.retrieve(page_id=project_page_id)

        subject_prop = project_page["properties"].get("과목")

        if not subject_prop:
            print("get_subject: 프로젝트 페이지에 '과목'속성이 없음")
            _project_subject_cache[project_page_id] = None
            return None

        prop_type = subject_prop.get("type")

        if prop_type == "select":
            select_value = subject_prop.get("select")
            subject = select_value["name"] if select_value else None

        elif prop_type == "multi_select":
            multi_list = subject_prop.get("multi_select") or []
            subject = multi_list[0]["name"] if multi_list else None

        elif prop_type == "rich_text":
            rich_text_list = subject_prop.get("rich_text") or []
            subject = rich_text_list[0]["plain_text"] if rich_text_list else None

        elif prop_type == "title":
            title_list = subject_prop.get("title") or []
            subject = title_list[0]["plain_text"] if title_list else None

        else:
            print("get_subject: 처리하지 않은 프로젝트 '과목' property type:", prop_type)
            subject = None

        _project_subject_cache[project_page_id] = subject
        return subject

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