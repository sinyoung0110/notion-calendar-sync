from notion_client import Client
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import json
import time
import random


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
# Google API 호출용 재시도 헬퍼
# =====================
#
# Calendar API를 짧은 시간에 여러 번 연달아 호출하면
# "Rate Limit Exceeded" (403/429) 에러가 날 수 있습니다.
# 이 헬퍼는 그런 경우 자동으로 잠깐 기다렸다가 재시도합니다.

def call_with_backoff(request_func, max_retries=5, base_delay=1.0):
    for attempt in range(max_retries):
        try:
            return request_func()
        except HttpError as e:
            status = e.resp.status if hasattr(e, "resp") else None
            reason = str(e)

            is_rate_limit = status in (403, 429) and (
                "rateLimitExceeded" in reason
                or "userRateLimitExceeded" in reason
                or "Rate Limit Exceeded" in reason
            )

            if is_rate_limit and attempt < max_retries - 1:
                wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                print(f"  -> Rate limit 감지, {wait:.1f}초 대기 후 재시도 ({attempt + 1}/{max_retries})")
                time.sleep(wait)
                continue

            # rate limit이 아니거나, 재시도 다 썼으면 그대로 에러 발생시킴
            raise

    raise RuntimeError("최대 재시도 횟수를 초과했습니다.")


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
        relation_prop = props.get("프로젝트 이름")

        if not relation_prop or relation_prop.get("type") != "relation":
            return None

        relation_list = relation_prop.get("relation") or []

        if not relation_list:
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
count_error = 0


for page in results["results"]:

    props = page["properties"]
    title = None

    try:

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

            call_with_backoff(lambda: calendar.events().update(
                calendarId="primary",
                eventId=event_id,
                body=event
            ).execute())

            count_update += 1


        # =====================
        # 신규 생성
        # =====================

        else:

            print("생성:", title)

            created = call_with_backoff(lambda: calendar.events().insert(
                calendarId="primary",
                body=event
            ).execute())

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

        # Calendar API 연속 호출 사이에 약간의 간격을 둬서
        # Rate Limit에 걸릴 확률 자체를 낮춥니다.
        time.sleep(0.3)

    except Exception as e:
        # 어떤 페이지에서 어떤 에러가 났는지 명확히 남기고,
        # 한 건이 실패해도 전체 스크립트는 계속 진행합니다.
        print(f"!! 처리 실패 - 제목: {title!r}, 페이지 ID: {page.get('id')}")
        print(f"   에러: {type(e).__name__}: {e}")
        count_error += 1
        continue


print("\n================")
print("생성:", count_create)
print("수정:", count_update)
print("건너뜀(시간 없음):", count_skip)
print("실패:", count_error)
print("================")