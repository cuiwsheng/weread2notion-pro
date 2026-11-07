#!/usr/bin/env python3
"""
Test script to diagnose reading progress/time sync issue.
验证 WeRead API 返回的数据结构和字段名称。
"""
import os
import sys
import json
import logging

logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(levelname)s] %(message)s')

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

def test_weread_api_response():
    """测试 WeRead API 响应结构"""
    from weread_api import WeReadApi
    
    try:
        api = WeReadApi()
        logging.info("✓ WeReadApi 初始化成功")
        
        # Get a sample book from notebooks
        logging.info("获取笔记本列表...")
        notebooks = api.get_notebooklist()
        if not notebooks:
            logging.error("✗ 没有找到任何笔记本")
            return False
        
        logging.info(f"✓ 找到 {len(notebooks)} 本书")
        
        # Test with first book
        test_book = notebooks[0]
        book_id = test_book.get("bookId")
        book_title = test_book.get("book", {}).get("title") or test_book.get("title", "未知")
        
        logging.info(f"\n测试书籍: {book_title} (ID: {book_id})")
        logging.info(f"笔记本原始数据: {json.dumps(test_book, ensure_ascii=False, indent=2)}")
        
        # Call get_read_info and inspect the raw API response
        logging.info("\n调用 get_read_info...")
        
        # Temporarily patch _call to see raw response
        original_call = api._call
        raw_response = {}
        
        def patched_call(api_name, **params):
            nonlocal raw_response
            result = original_call(api_name, **params)
            if api_name == "/book/getprogress":
                raw_response = result
            return result
        
        api._call = patched_call
        read_info = api.get_read_info(book_id)
        api._call = original_call
        
        logging.info(f"\nAPI 原始响应 (/book/getprogress):")
        logging.info(json.dumps(raw_response, ensure_ascii=False, indent=2))
        
        logging.info(f"\n规范化后的 read_info:")
        logging.info(json.dumps(read_info, ensure_ascii=False, indent=2))
        
        # Check if progress and reading time are present
        progress = read_info.get("readingProgress")
        reading_time = read_info.get("readingTime")
        
        logging.info(f"\n检查结果:")
        logging.info(f"  阅读进度: {progress}")
        logging.info(f"  阅读时长: {reading_time}")
        
        if progress is None and reading_time is None:
            logging.error("✗ 阅读进度和阅读时长都是 None")
            return False
        elif progress == 0 and reading_time == 0:
            logging.warning("⚠ 阅读进度和阅读时长都是 0（可能正常，也可能是字段映射错误）")
            logging.warning("  检查原始 API 响应中的字段名称")
        else:
            logging.info("✓ 成功获取阅读进度和时长")
        
        return True
        
    except Exception as e:
        logging.error(f"✗ 测试失败: {e}", exc_info=True)
        return False

def test_notion_update():
    """测试 Notion 更新逻辑"""
    from config import book_properties_type_dict, NUMBER
    import utils
    
    logging.info("\n测试 Notion 属性映射...")
    
    # Simulate book data
    book = {
        "阅读进度": 0.75,  # 75%
        "阅读时长": 3600,  # 1 hour in seconds
    }
    
    logging.info(f"测试数据: {book}")
    
    properties = utils.get_properties(book, book_properties_type_dict)
    
    logging.info(f"生成的 Notion properties:")
    logging.info(json.dumps(properties, ensure_ascii=False, indent=2))
    
    # Check if properties were created correctly
    if "阅读进度" in properties and "阅读时长" in properties:
        logging.info("✓ 属性映射正确")
        return True
    else:
        logging.error("✗ 属性映射失败")
        return False

if __name__ == "__main__":
    logging.info("=" * 60)
    logging.info("WeRead 阅读进度/时长同步问题诊断")
    logging.info("=" * 60)
    
    success = True
    
    # Test 1: WeRead API response structure
    logging.info("\n[测试 1] WeRead API 响应结构")
    if not test_weread_api_response():
        success = False
    
    # Test 2: Notion property mapping
    logging.info("\n[测试 2] Notion 属性映射")
    if not test_notion_update():
        success = False
    
    logging.info("\n" + "=" * 60)
    if success:
        logging.info("✓ 所有测试通过")
        sys.exit(0)
    else:
        logging.error("✗ 部分测试失败，请检查上述输出")
        sys.exit(1)
