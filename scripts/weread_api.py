import hashlib
import os
import re

import pendulum
import requests
from retrying import retry

WEREAD_GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
SKILL_VERSION = "1.0.3"


class WeReadApi:
    """WeRead Agent API gateway client (skills API)."""

    def __init__(self):
        self.api_key = os.getenv("WEREAD_API_KEY", "").strip()
        if not self.api_key:
            raise Exception(
                "未找到 WEREAD_API_KEY，请在 GitHub Secrets 或环境变量中配置"
                "微信读书 API Key（格式 wrk-xxxxxxxx）"
            )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
        )

    def _call(self, api_name, **params):
        body = {"api_name": api_name, "skill_version": SKILL_VERSION, **params}
        r = self.session.post(WEREAD_GATEWAY_URL, json=body, timeout=60)
        if not r.ok:
            raise Exception(f"Gateway HTTP {r.status_code}: {r.text[:500]}")
        data = r.json()
        errcode = data.get("errcode", 0)
        if errcode != 0:
            errmsg = data.get("errmsg") or data.get("errlog") or str(data)
            raise Exception(f"WeRead API {api_name} failed ({errcode}): {errmsg}")
        if "upgrade_info" in data:
            msg = data["upgrade_info"].get("message", "请升级 weread-skills 版本")
            raise Exception(f"技能版本需升级: {msg}")
        return data

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookshelf(self):
        data = self._call("/shelf/sync")
        if "bookProgress" not in data and data.get("books"):
            data["bookProgress"] = [
                {
                    "bookId": b.get("bookId"),
                    "readingTime": b.get("recordReadingTime")
                    or b.get("readingTime")
                    or 0,
                }
                for b in data["books"]
                if b.get("bookId")
            ]
        return data

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_notebooklist(self):
        books = []
        last_sort = None
        while True:
            params = {"count": 100}
            if last_sort is not None:
                params["lastSort"] = last_sort
            data = self._call("/user/notebooks", **params)
            page = data.get("books") or []
            books.extend(page)
            if not data.get("hasMore"):
                break
            if not page:
                break
            last_sort = page[-1].get("sort")
            if last_sort is None:
                break
        books.sort(key=lambda x: x.get("sort", 0))
        return books

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookinfo(self, bookId):
        data = self._call("/book/info", bookId=bookId)
        if data.get("bookId") or data.get("title"):
            return data
        book = data.get("book")
        return book if book else data

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_bookmark_list(self, bookId):
        data = self._call("/book/bookmarklist", bookId=bookId)
        return data.get("updated") or []

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_read_info(self, bookId):
        """Normalize /book/getprogress to legacy readinfo shape for book.py."""
        data = self._call("/book/getprogress", bookId=bookId)
        book = data.get("book") or {}
        progress = book.get("progress", 0) or 0
        reading_time = book.get("recordReadingTime", 0) or 0
        finish_time = book.get("finishTime")
        marked_status = 4 if progress >= 100 or finish_time else 1
        return {
            "readingProgress": progress,
            "readingTime": reading_time,
            "markedStatus": marked_status,
            "beginReadingDate": None,
            "lastReadingDate": book.get("updateTime"),
            "readingBookDate": book.get("updateTime"),
            "finishedDate": finish_time,
            "readDetail": {},
            "bookInfo": {},
        }

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_review_list(self, bookId):
        reviews = []
        synckey = 0
        while True:
            data = self._call(
                "/review/list/mine", bookid=bookId, synckey=synckey, count=100
            )
            for item in data.get("reviews") or []:
                review = item.get("review") if isinstance(item, dict) else item
                if not review:
                    continue
                if review.get("type") == 4:
                    review = {"chapterUid": 1000000, **review}
                reviews.append(review)
            if not data.get("hasMore"):
                break
            synckey = data.get("synckey", 0)
        return reviews

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_api_data(self):
        """Monthly read times (legacy readTimes shape, values in seconds)."""
        data = self._call("/readdata/detail", mode="monthly", baseTime=0)
        read_times = data.get("readTimes") or data.get("dailyReadTimes") or {}
        return {"readTimes": {str(k): v for k, v in read_times.items()}}

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_read_times_for_year(self, year):
        """Daily read times for a calendar year (seconds per day)."""
        base = pendulum.datetime(int(year), 6, 15, tz="Asia/Shanghai").int_timestamp
        data = self._call("/readdata/detail", mode="annually", baseTime=base)
        read_times = data.get("dailyReadTimes") or data.get("readTimes") or {}
        return {str(k): v for k, v in read_times.items()}

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_chapter_info(self, bookId):
        data = self._call("/book/chapterinfo", bookId=bookId)
        chapters = data.get("chapters") or []
        update = [
            {
                "chapterUid": c.get("chapterUid"),
                "chapterIdx": c.get("chapterIdx"),
                "updateTime": c.get("updateTime"),
                "readAhead": 0,
                "title": c.get("title"),
                "level": c.get("level", 1),
            }
            for c in chapters
        ]
        update.append(
            {
                "chapterUid": 1000000,
                "chapterIdx": 1000000,
                "updateTime": 1683825006,
                "readAhead": 0,
                "title": "点评",
                "level": 1,
            }
        )
        return {item["chapterUid"]: item for item in update if item.get("chapterUid")}

    def transform_id(self, book_id):
        id_length = len(book_id)
        if re.match(r"^\d*$", book_id):
            ary = []
            for i in range(0, id_length, 9):
                ary.append(format(int(book_id[i : min(i + 9, id_length)]), "x"))
            return "3", ary

        result = ""
        for i in range(id_length):
            result += format(ord(book_id[i]), "x")
        return "4", [result]

    def calculate_book_str_id(self, book_id):
        md5 = hashlib.md5()
        md5.update(book_id.encode("utf-8"))
        digest = md5.hexdigest()
        result = digest[0:3]
        code, transformed_ids = self.transform_id(book_id)
        result += code + "2" + digest[-2:]

        for i in range(len(transformed_ids)):
            hex_length_str = format(len(transformed_ids[i]), "x")
            if len(hex_length_str) == 1:
                hex_length_str = "0" + hex_length_str
            result += hex_length_str + transformed_ids[i]
            if i < len(transformed_ids) - 1:
                result += "g"

        if len(result) < 20:
            result += digest[0 : 20 - len(result)]

        md5 = hashlib.md5()
        md5.update(result.encode("utf-8"))
        result += md5.hexdigest()[0:3]
        return result

    def get_url(self, book_id):
        return f"https://weread.qq.com/web/reader/{self.calculate_book_str_id(book_id)}"
