from notion_client import Client
import os
notion = os.environ["NOTION_TOKEN"]
data_source_id = "e4f96717-d484-82a5-8212-0719c35b885a"

results = notion.data_sources.query(
    data_source_id=data_source_id
)

for page in results["results"]:
    props = page["properties"]

    title = props["ToDo"]["title"][0]["plain_text"] if props["ToDo"]["title"] else ""

    start = props["시작 시간"]["date"]
    end_formula = props["시작~종료"]["formula"]

    print("----")
    print("제목:", title)
    print("시작:", start)
    print("종료 Formula:", end_formula)