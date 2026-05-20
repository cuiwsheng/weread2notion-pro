import json
import os
from datetime import datetime, timedelta

import pendulum

from notion_helper import NotionHelper
from weread_api import WeReadApi
from utils import (
    format_date,
    get_date,
    get_icon,
    get_number,
    get_relation,
    get_title,
)

def insert_to_notion(helper, page_id, timestamp, duration):
    parent = {"database_id": helper.day_database_id, "type": "database_id"}
    properties = {
        "标题": get_title(
            format_date(
                datetime.utcfromtimestamp(timestamp) + timedelta(hours=8),
                "%Y年%m月%d日",
            )
        ),
        "日期": get_date(
            start=format_date(datetime.utcfromtimestamp(timestamp) + timedelta(hours=8))
        ),
        "时长": get_number(duration),
        "时间戳": get_number(timestamp),
        "年": get_relation(
            [
                helper.get_year_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
        "月": get_relation(
            [
                helper.get_month_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
        "周": get_relation(
            [
                helper.get_week_relation_id(
                    datetime.utcfromtimestamp(timestamp) + timedelta(hours=8)
                ),
            ]
        ),
    }
    if page_id is not None:
        helper.client.pages.update(page_id=page_id, properties=properties)
    else:
        helper.client.pages.create(
            parent=parent,
            icon=get_icon("https://www.notion.so/icons/target_red.svg"),
            properties=properties,
        )


def sync_read_times_to_notion(helper, read_times):
    """Upsert daily reading seconds into Notion day database."""
    read_times = {int(k): v for k, v in read_times.items()}
    now = pendulum.now("Asia/Shanghai").start_of("day")
    today_timestamp = now.int_timestamp
    if today_timestamp not in read_times:
        read_times[today_timestamp] = 0
    read_times = dict(sorted(read_times.items()))
    results = helper.query_all(database_id=helper.day_database_id)
    for result in results:
        timestamp = result.get("properties").get("时间戳").get("number")
        duration = result.get("properties").get("时长").get("number")
        page_id = result.get("id")
        if timestamp in read_times:
            value = read_times.pop(timestamp)
            if value != duration:
                insert_to_notion(
                    helper, page_id=page_id, timestamp=timestamp, duration=value
                )
    for key, value in read_times.items():
        insert_to_notion(helper, None, int(key), value)


def export_heatmap_json(helper, year, read_times_seconds=None):
    """Build OUT_FOLDER/data.json (date -> minutes) from API + Notion day DB."""
    os.makedirs("OUT_FOLDER", exist_ok=True)
    year_int = int(year)
    year_start = pendulum.datetime(year_int, 1, 1, tz="Asia/Shanghai")
    year_end = pendulum.datetime(year_int, 12, 31, tz="Asia/Shanghai").end_of("day")
    start_ts = year_start.int_timestamp
    end_ts = year_end.int_timestamp

    tracks = {}
    if read_times_seconds:
        for ts, seconds in read_times_seconds.items():
            ts = int(ts)
            if not (start_ts <= ts <= end_ts):
                continue
            date_str = pendulum.from_timestamp(ts, tz="Asia/Shanghai").to_date_string()
            tracks[date_str] = round(seconds / 60.0, 2)

    results = helper.query_all(database_id=helper.day_database_id)
    for result in results:
        props = result.get("properties") or {}
        timestamp = props.get("时间戳", {}).get("number")
        duration = props.get("时长", {}).get("number")
        if timestamp is None or duration is None:
            continue
        if not (start_ts <= timestamp <= end_ts):
            continue
        date_str = pendulum.from_timestamp(timestamp, tz="Asia/Shanghai").to_date_string()
        tracks[date_str] = round(duration / 60.0, 2)

    out_path = os.path.join("OUT_FOLDER", "data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False)
    print(f"Wrote heatmap data: {out_path} ({len(tracks)} days)")
    return out_path


HEATMAP_GUIDE = (
    "https://mp.weixin.qq.com/s?__biz=MzI1OTcxOTI4NA==&mid=2247484145&idx=1&sn="
    "81752852420b9153fc292b7873217651&chksm=ea75ebeadd0262fc65df100370d3f983ba2e52e2fcde2deb1ed49343fbb10645a77570656728&token=157143379&lang=zh_CN#rd"
)

def update_heatmap_embed(helper):
    image_file = None
    folder_path = "./OUT_FOLDER"
    if os.path.isdir(folder_path):
        for name in os.listdir(folder_path):
            if name.endswith(".svg"):
                image_file = name
                break

    if image_file:
        image_url = (
            f"https://raw.githubusercontent.com/{os.getenv('REPOSITORY')}/"
            f"{os.getenv('REF', 'refs/heads/main').split('/')[-1]}/OUT_FOLDER/{image_file}"
        )
        heatmap_url = f"https://heatmap.malinkang.com/?image={image_url}"
        if helper.heatmap_block_id:
            helper.update_heatmap(block_id=helper.heatmap_block_id, url=heatmap_url)
        else:
            print(f"更新热力图失败，没有添加热力图占位。具体参考：{HEATMAP_GUIDE}")
    else:
        print(f"未找到热力图 SVG。占位说明：{HEATMAP_GUIDE}")


if __name__ == "__main__":
    helper = NotionHelper()

    if os.getenv("HEATMAP_UPDATE_ONLY") == "1":
        update_heatmap_embed(helper)
        raise SystemExit(0)

    weread_api = WeReadApi()
    year = os.getenv("YEAR") or str(pendulum.now("Asia/Shanghai").year)

    read_times = {}
    try:
        annual = weread_api.get_read_times_for_year(year)
        read_times.update({int(k): v for k, v in annual.items()})
    except Exception as e:
        print(f"Annual readdata fetch skipped: {e}")

    monthly = weread_api.get_api_data().get("readTimes") or {}
    read_times.update({int(k): v for k, v in monthly.items()})

    sync_read_times_to_notion(helper, read_times)
    export_heatmap_json(helper, year, read_times_seconds=read_times)
