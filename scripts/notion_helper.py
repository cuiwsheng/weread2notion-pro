import logging
import os
import re
import time

from notion_client import Client
from notion_client.errors import APIResponseError
from retrying import retry
from datetime import timedelta
from dotenv import load_dotenv
from utils import (
    format_date,
    get_date,
    get_first_and_last_day_of_month,
    get_first_and_last_day_of_week,
    get_first_and_last_day_of_year,
    get_icon,
    get_number,
    get_relation,
    get_rich_text,
    get_title,
    timestamp_to_date,
    get_property_value,
)

load_dotenv()
TAG_ICON_URL = "https://www.notion.so/icons/tag_gray.svg"
USER_ICON_URL = "https://www.notion.so/icons/user-circle-filled_gray.svg"
TARGET_ICON_URL = "https://www.notion.so/icons/target_red.svg"
BOOKMARK_ICON_URL = "https://www.notion.so/icons/bookmark_gray.svg"


class NotionHelper:
    database_name_dict = {
        "BOOK_DATABASE_NAME": "书架",
        "CHAPTER_DATABASE_NAME": "章节",
        "READ_DATABASE_NAME": "阅读记录",
    }
    database_id_dict = {}
    heatmap_block_id = None
    property_dict = {}

    def __init__(self):
        self.client = Client(auth=os.getenv("NOTION_TOKEN"), log_level=logging.ERROR)
        self.__cache = {}
        for key in self.database_name_dict.keys():
            if os.getenv(key) not in (None, ""):
                self.database_name_dict[key] = os.getenv(key)
        heatmap_block_id = os.getenv("HEATMAP_BLOCK_ID", "").strip()
        if heatmap_block_id:
            self.heatmap_block_id = self.normalize_notion_id(heatmap_block_id)
        self.page_id = self.extract_page_id(os.getenv("NOTION_PAGE"))
        self._discover_databases()
        self.book_database_id = self.database_id_dict.get(
            self.database_name_dict.get("BOOK_DATABASE_NAME")
        )
        if not self.book_database_id:
            raise Exception(
                "未找到「书架」数据库。请任选其一：\n"
                "1) NOTION_PAGE 设为包含「书架」子库的父页面 URL，并授权集成 WeReadPro；\n"
                "2) NOTION_PAGE 直接填「书架」数据库的 URL；\n"
                "3) 在 Secrets 中设置 BOOK_DATABASE_ID 为书架数据库 ID。\n"
                f"当前 page_id={self.page_id}，BOOK_DATABASE_NAME="
                f"{self.database_name_dict.get('BOOK_DATABASE_NAME')}"
            )
        r = self.client.databases.retrieve(database_id=self.book_database_id)
        for key, value in r.get("properties").items():
            self.property_dict[key] = value
        self.review_database_id = self.get_relation_database_id(
            self.property_dict.get("读书笔记")
        )
        self.bookmark_database_id = self.get_relation_database_id(
            self.property_dict.get("划线")
        )
        self.day_database_id = self.get_relation_database_id(
            self.property_dict.get("日")
        )
        self.week_database_id = self.get_relation_database_id(
            self.property_dict.get("周")
        )
        self.month_database_id = self.get_relation_database_id(
            self.property_dict.get("月")
        )
        self.year_database_id = self.get_relation_database_id(
            self.property_dict.get("年")
        )
        self.category_database_id = self.get_relation_database_id(
            self.property_dict.get("分类")
        )
        self.author_database_id = self.get_relation_database_id(
            self.property_dict.get("作者")
        )
        if "章节" in self.property_dict:
            self.chapter_database_id = self.get_relation_database_id(
                self.property_dict.get("章节")
            )
        else:
            self.chapter_database_id = self.database_id_dict.get(
                self.database_name_dict.get("CHAPTER_DATABASE_NAME")
            )
        if "阅读记录" in self.property_dict:
            self.read_database_id = self.get_relation_database_id(
                self.property_dict.get("阅读记录")
            )
        else:
            self.read_database_id = self.database_id_dict.get(
                self.database_name_dict.get("READ_DATABASE_NAME")
            )
        self.update_book_database()
        if self.read_database_id is None:
            self.create_database()

    def get_relation_database_id(self, property):
        return property.get("relation").get("database_id")

    @staticmethod
    def normalize_notion_id(raw_id):
        raw_id = (raw_id or "").strip().replace("-", "")
        if len(raw_id) != 32:
            return raw_id
        return (
            f"{raw_id[0:8]}-{raw_id[8:12]}-{raw_id[12:16]}-"
            f"{raw_id[16:20]}-{raw_id[20:32]}"
        )

    @staticmethod
    def _plain_title(title_prop):
        if isinstance(title_prop, str):
            return title_prop
        parts = []
        for item in title_prop or []:
            if item.get("type") == "text":
                parts.append(item.get("plain_text") or item.get("text", {}).get("content", ""))
        return "".join(parts)

    @staticmethod
    def _is_not_found_error(error):
        if isinstance(error, APIResponseError):
            return error.code in ("object_not_found", "validation_error")
        return "404" in str(error) or "not found" in str(error).lower()

    def extract_page_id(self, notion_url):
        if not notion_url or not str(notion_url).strip():
            raise Exception("NOTION_PAGE 未配置，请在 GitHub Secrets 中设置父页面 URL")
        notion_url = str(notion_url).strip().strip('"').strip("'")
        match = re.search(
            r"([a-f0-9]{32}|[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})",
            notion_url,
            re.IGNORECASE,
        )
        if match:
            return self.normalize_notion_id(match.group(0))
        raise Exception(f"获取 Notion ID 失败，请检查 NOTION_PAGE URL 是否正确: {notion_url}")

    def _apply_database_id_env_overrides(self):
        """Optional secrets: BOOK_DATABASE_ID, DAY_DATABASE_ID, etc."""
        env_map = {
            "BOOK_DATABASE_ID": "BOOK_DATABASE_NAME",
            "CHAPTER_DATABASE_ID": "CHAPTER_DATABASE_NAME",
            "READ_DATABASE_ID": "READ_DATABASE_NAME",
            "DAY_DATABASE_ID": "DAY_DATABASE_NAME",
            "WEEK_DATABASE_ID": "WEEK_DATABASE_NAME",
            "MONTH_DATABASE_ID": "MONTH_DATABASE_NAME",
            "YEAR_DATABASE_ID": "YEAR_DATABASE_NAME",
        }
        for env_key, name_key in env_map.items():
            raw_id = os.getenv(env_key, "").strip()
            if not raw_id:
                continue
            db_id = self.normalize_notion_id(raw_id)
            name = self.database_name_dict.get(name_key) or os.getenv(name_key, "")
            if name:
                self.database_id_dict[name] = db_id

    def _try_register_notion_id_as_book_database(self, notion_id):
        """NOTION_PAGE may be a database URL instead of a parent page."""
        try:
            db = self.client.databases.retrieve(database_id=notion_id)
        except Exception:
            return False
        title = self._plain_title(db.get("title"))
        book_name = self.database_name_dict.get("BOOK_DATABASE_NAME")
        if title:
            self.database_id_dict[title] = notion_id
        if book_name:
            self.database_id_dict[book_name] = notion_id
        return bool(book_name and self.database_id_dict.get(book_name))

    def _discover_databases(self):
        self._apply_database_id_env_overrides()
        book_name = self.database_name_dict.get("BOOK_DATABASE_NAME")
        if self.database_id_dict.get(book_name):
            return
        try:
            self.search_database(self.page_id)
        except Exception as error:
            if not self._is_not_found_error(error):
                raise
            print(
                f"警告: 无法遍历 Notion 页面 {self.page_id}（{error}），"
                "尝试其他方式发现数据库。"
            )
        if not self.database_id_dict.get(book_name):
            if self._try_register_notion_id_as_book_database(self.page_id):
                print(f"已将 NOTION_PAGE 识别为数据库「{book_name}」。")
            else:
                self._discover_databases_via_search()
        if not self.database_id_dict.get(book_name):
            self._discover_databases_via_search()

    def _list_accessible_data_sources(self):
        """List data sources/databases visible to the integration (Notion API 2025+)."""
        catalog = {}
        start_cursor = None
        while True:
            kwargs = {
                "filter": {"property": "object", "value": "data_source"},
                "page_size": 100,
            }
            if start_cursor:
                kwargs["start_cursor"] = start_cursor
            response = self.client.search(**kwargs)
            for item in response.get("results", []):
                if item.get("object") not in ("database", "data_source"):
                    continue
                title = self._plain_title(item.get("title"))
                if title and title not in catalog:
                    catalog[title] = item["id"]
            if not response.get("has_more"):
                break
            start_cursor = response.get("next_cursor")
        return catalog

    def _discover_databases_via_search(self):
        catalog = self._list_accessible_data_sources()
        names = set(self.database_name_dict.values())
        names.update(["日", "周", "月", "年", "划线", "读书笔记", "章节", "分类", "作者"])
        for name in names:
            if name and name not in self.database_id_dict and name in catalog:
                self.database_id_dict[name] = catalog[name]
        if catalog and not self.database_id_dict:
            print(
                "已搜索到以下数据库，但未匹配到「书架」："
                + ", ".join(sorted(catalog.keys()))
            )

    def _search_database_by_title(self, title):
        catalog = self._list_accessible_data_sources()
        return catalog.get(title)

    def search_database(self, block_id):
        children = self.client.blocks.children.list(block_id=block_id)["results"]
        # 遍历子块
        for child in children:
            # 检查子块的类型
            if child["type"] == "child_database":
                title = self._plain_title(child.get("child_database", {}).get("title"))
                if title:
                    self.database_id_dict[title] = child.get("id")
            elif child["type"] == "embed" and child.get("embed").get("url"):
                if (
                    child.get("embed")
                    .get("url")
                    .startswith("https://heatmap.malinkang.com/")
                ):
                    self.heatmap_block_id = child.get("id")
            # 如果子块有子块，递归调用函数
            if "has_children" in child and child["has_children"]:
                self.search_database(child["id"])

    def update_book_database(self):
        """更新数据库"""
        response = self.client.databases.retrieve(database_id=self.book_database_id)
        id = response.get("id")
        properties = response.get("properties")
        update_properties = {}
        if (
            properties.get("阅读时长") is None
            or properties.get("阅读时长").get("type") != "number"
        ):
            update_properties["阅读时长"] = {"number": {}}
        if (
            properties.get("书架分类") is None
            or properties.get("书架分类").get("type") != "select"
        ):
            update_properties["书架分类"] = {"select": {}}
        if (
            properties.get("豆瓣链接") is None
            or properties.get("豆瓣链接").get("type") != "url"
        ):
            update_properties["豆瓣链接"] = {"url": {}}
        if (
            properties.get("我的评分") is None
            or properties.get("我的评分").get("type") != "select"
        ):
            update_properties["我的评分"] = {"select": {}}
        if (
            properties.get("豆瓣短评") is None
            or properties.get("豆瓣短评").get("type") != "rich_text"
        ):
            update_properties["豆瓣短评"] = {"rich_text": {}}
        """NeoDB先不添加了，现在受众还不广，可能有的小伙伴不知道是干什么的"""
        # if properties.get("NeoDB链接") is None or properties.get("NeoDB链接").get("type") != "url":
        #     update_properties["NeoDB链接"] = {"url": {}}
        if len(update_properties) > 0:
            self.client.databases.update(database_id=id, properties=update_properties)

    def create_database(self):
        title = [
            {
                "type": "text",
                "text": {
                    "content": self.database_name_dict.get("READ_DATABASE_NAME"),
                },
            },
        ]
        properties = {
            "标题": {"title": {}},
            "时长": {"number": {}},
            "时间戳": {"number": {}},
            "日期": {"date": {}},
            "书架": {
                "relation": {
                    "database_id": self.book_database_id,
                    "single_property": {},
                }
            },
        }
        parent = parent = {"page_id": self.page_id, "type": "page_id"}
        self.read_database_id = self.client.databases.create(
            parent=parent,
            title=title,
            icon=get_icon("https://www.notion.so/icons/target_gray.svg"),
            properties=properties,
        ).get("id")

    def update_heatmap(self, block_id, url):
        # 更新 image block 的链接
        return self.client.blocks.update(block_id=block_id, embed={"url": url})

    def get_week_relation_id(self, date):
        year = date.isocalendar().year
        week = date.isocalendar().week
        week = f"{year}年第{week}周"
        start, end = get_first_and_last_day_of_week(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            week, self.week_database_id, TARGET_ICON_URL, properties
        )

    def get_month_relation_id(self, date):
        month = date.strftime("%Y年%-m月")
        start, end = get_first_and_last_day_of_month(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            month, self.month_database_id, TARGET_ICON_URL, properties
        )

    def get_year_relation_id(self, date):
        year = date.strftime("%Y")
        start, end = get_first_and_last_day_of_year(date)
        properties = {"日期": get_date(format_date(start), format_date(end))}
        return self.get_relation_id(
            year, self.year_database_id, TARGET_ICON_URL, properties
        )

    def get_day_relation_id(self, date):
        new_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        timestamp = (new_date - timedelta(hours=8)).timestamp()
        day = new_date.strftime("%Y年%m月%d日")
        properties = {
            "日期": get_date(format_date(date)),
            "时间戳": get_number(timestamp),
        }
        properties["年"] = get_relation(
            [
                self.get_year_relation_id(new_date),
            ]
        )
        properties["月"] = get_relation(
            [
                self.get_month_relation_id(new_date),
            ]
        )
        properties["周"] = get_relation(
            [
                self.get_week_relation_id(new_date),
            ]
        )
        return self.get_relation_id(
            day, self.day_database_id, TARGET_ICON_URL, properties
        )

    def get_relation_id(self, name, id, icon, properties={}):
        key = f"{id}{name}"
        if key in self.__cache:
            return self.__cache.get(key)
        filter = {"property": "标题", "title": {"equals": name}}
        response = self.client.databases.query(database_id=id, filter=filter)
        if len(response.get("results")) == 0:
            parent = {"database_id": id, "type": "database_id"}
            properties["标题"] = get_title(name)
            page_id = self.client.pages.create(
                parent=parent, properties=properties, icon=get_icon(icon)
            ).get("id")
        else:
            page_id = response.get("results")[0].get("id")
        self.__cache[key] = page_id
        return page_id

    def insert_bookmark(self, id, bookmark):
        icon = get_icon(BOOKMARK_ICON_URL)
        properties = {
            "Name": get_title(bookmark.get("markText", "")),
            "bookId": get_rich_text(bookmark.get("bookId")),
            "range": get_rich_text(bookmark.get("range")),
            "bookmarkId": get_rich_text(bookmark.get("bookmarkId")),
            "blockId": get_rich_text(bookmark.get("blockId")),
            "chapterUid": get_number(bookmark.get("chapterUid")),
            "bookVersion": get_number(bookmark.get("bookVersion")),
            "colorStyle": get_number(bookmark.get("colorStyle")),
            "type": get_number(bookmark.get("type")),
            "style": get_number(bookmark.get("style")),
            "书籍": get_relation([id]),
        }
        if "createTime" in bookmark:
            create_time = timestamp_to_date(int(bookmark.get("createTime")))
            properties["Date"] = get_date(create_time.strftime("%Y-%m-%d %H:%M:%S"))
            self.get_date_relation(properties, create_time)
        parent = {"database_id": self.bookmark_database_id, "type": "database_id"}
        self.create_page(parent, properties, icon)

    def insert_review(self, id, review):
        time.sleep(0.1)
        icon = get_icon(TAG_ICON_URL)
        properties = {
            "Name": get_title(review.get("content", "")),
            "bookId": get_rich_text(review.get("bookId")),
            "reviewId": get_rich_text(review.get("reviewId")),
            "blockId": get_rich_text(review.get("blockId")),
            "chapterUid": get_number(review.get("chapterUid")),
            "bookVersion": get_number(review.get("bookVersion")),
            "type": get_number(review.get("type")),
            "书籍": get_relation([id]),
        }
        if "range" in review:
            properties["range"] = get_rich_text(review.get("range"))
        if "star" in review:
            properties["star"] = get_number(review.get("star"))
        if "abstract" in review:
            properties["abstract"] = get_rich_text(review.get("abstract"))
        if "createTime" in review:
            create_time = timestamp_to_date(int(review.get("createTime")))
            properties["Date"] = get_date(create_time.strftime("%Y-%m-%d %H:%M:%S"))
            self.get_date_relation(properties, create_time)
        parent = {"database_id": self.review_database_id, "type": "database_id"}
        self.create_page(parent, properties, icon)

    def insert_chapter(self, id, chapter):
        time.sleep(0.1)
        icon = {"type": "external", "external": {"url": TAG_ICON_URL}}
        properties = {
            "Name": get_title(chapter.get("title")),
            "blockId": get_rich_text(chapter.get("blockId")),
            "chapterUid": {"number": chapter.get("chapterUid")},
            "chapterIdx": {"number": chapter.get("chapterIdx")},
            "readAhead": {"number": chapter.get("readAhead")},
            "updateTime": {"number": chapter.get("updateTime")},
            "level": {"number": chapter.get("level")},
            "书籍": {"relation": [{"id": id}]},
        }
        parent = {"database_id": self.chapter_database_id, "type": "database_id"}
        self.create_page(parent, properties, icon)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_book_page(self, page_id, properties):
        return self.client.pages.update(page_id=page_id, properties=properties)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def update_page(self, page_id, properties, cover):
        return self.client.pages.update(
            page_id=page_id, properties=properties, cover=cover
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def create_page(self, parent, properties, icon):
        return self.client.pages.create(parent=parent, properties=properties, icon=icon)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def create_book_page(self, parent, properties, icon):
        return self.client.pages.create(
            parent=parent, properties=properties, icon=icon, cover=icon
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query(self, **kwargs):
        kwargs = {k: v for k, v in kwargs.items() if v}
        return self.client.databases.query(**kwargs)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_block_children(self, id):
        response = self.client.blocks.children.list(id)
        return response.get("results")

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks(self, block_id, children):
        return self.client.blocks.children.append(block_id=block_id, children=children)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def append_blocks_after(self, block_id, children, after):
        return self.client.blocks.children.append(
            block_id=block_id, children=children, after=after
        )

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def delete_block(self, block_id):
        return self.client.blocks.delete(block_id=block_id)

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def get_all_book(self):
        """从Notion中获取所有的书籍"""
        results = self.query_all(self.book_database_id)
        books_dict = {}
        for result in results:
            bookId = get_property_value(result.get("properties").get("BookId"))
            books_dict[bookId] = {
                "pageId": result.get("id"),
                "readingTime": get_property_value(
                    result.get("properties").get("阅读时长")
                ),
                "category": get_property_value(
                    result.get("properties").get("书架分类")
                ),
                "Sort": get_property_value(result.get("properties").get("Sort")),
                "douban_url": get_property_value(
                    result.get("properties").get("豆瓣链接")
                ),
                "cover": result.get("cover"),
                "myRating": get_property_value(
                    result.get("properties").get("我的评分")
                ),
                "comment": get_property_value(result.get("properties").get("豆瓣短评")),
                "status": get_property_value(result.get("properties").get("阅读状态")),
            }
        return books_dict

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all_by_book(self, database_id, filter):
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.databases.query(
                database_id=database_id,
                filter=filter,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results"))
        return results

    @retry(stop_max_attempt_number=3, wait_fixed=5000)
    def query_all(self, database_id):
        """获取database中所有的数据"""
        results = []
        has_more = True
        start_cursor = None
        while has_more:
            response = self.client.databases.query(
                database_id=database_id,
                start_cursor=start_cursor,
                page_size=100,
            )
            start_cursor = response.get("next_cursor")
            has_more = response.get("has_more")
            results.extend(response.get("results"))
        return results

    def get_date_relation(self, properties, date):
        properties["年"] = get_relation(
            [
                self.get_year_relation_id(date),
            ]
        )
        properties["月"] = get_relation(
            [
                self.get_month_relation_id(date),
            ]
        )
        properties["周"] = get_relation(
            [
                self.get_week_relation_id(date),
            ]
        )
        properties["日"] = get_relation(
            [
                self.get_day_relation_id(date),
            ]
        )
