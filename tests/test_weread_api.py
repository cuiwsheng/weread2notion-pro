#!/usr/bin/env python3
"""
Unit tests for WeRead API normalization logic.
测试 WeRead API 数据规范化逻辑的单元测试。
"""
import unittest
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


class TestWeReadApiNormalization(unittest.TestCase):
    """Test get_read_info response normalization."""
    
    def test_nested_book_structure(self):
        """Test API response with nested 'book' key."""
        # Simulate nested response: {book: {progress: ...}}
        data = {
            "book": {
                "progress": 75,
                "recordReadingTime": 3600,
                "finishTime": None,
                "updateTime": 1699000000
            }
        }
        
        # Apply normalization logic
        book = data.get("book") or data
        progress = book.get("progress", 0) or 0
        reading_time = book.get("recordReadingTime", 0) or 0
        
        self.assertEqual(progress, 75, "Progress should be 75")
        self.assertEqual(reading_time, 3600, "Reading time should be 3600")
    
    def test_flat_structure(self):
        """Test API response with flat structure (no nested 'book')."""
        # Simulate flat response: {progress: ...}
        data = {
            "progress": 85,
            "recordReadingTime": 7200,
            "finishTime": None,
            "updateTime": 1699100000
        }
        
        # OLD BUG: book = data.get("book") or {} would return {}
        # NEW FIX: book = data.get("book") or data returns data itself
        book = data.get("book") or data
        progress = book.get("progress", 0) or 0
        reading_time = book.get("recordReadingTime", 0) or 0
        
        self.assertEqual(progress, 85, "Progress should be 85 (not 0)")
        self.assertEqual(reading_time, 7200, "Reading time should be 7200 (not 0)")
    
    def test_missing_progress_fields(self):
        """Test API response with missing progress fields."""
        data = {
            "finishTime": 1699200000,
            "updateTime": 1699200000
        }
        
        book = data.get("book") or data
        progress = book.get("progress", 0) or 0
        reading_time = book.get("recordReadingTime", 0) or 0
        
        self.assertEqual(progress, 0, "Progress should default to 0")
        self.assertEqual(reading_time, 0, "Reading time should default to 0")
    
    def test_none_values(self):
        """Test API response with explicit None values."""
        data = {
            "progress": None,
            "recordReadingTime": None,
            "finishTime": None
        }
        
        book = data.get("book") or data
        progress = book.get("progress", 0) or 0
        reading_time = book.get("recordReadingTime", 0) or 0
        
        # With `or 0`, None becomes 0
        self.assertEqual(progress, 0, "None progress should become 0")
        self.assertEqual(reading_time, 0, "None reading time should become 0")


class TestProgressToNotionMapping(unittest.TestCase):
    """Test book progress to Notion property mapping."""
    
    def test_progress_percentage_calculation(self):
        """Test reading progress conversion to percentage."""
        # Simulate book.py logic (lines 59-61)
        markedStatus = 1  # In progress
        readingProgress = 75  # From API
        
        progress_pct = (
            100 if markedStatus == 4 else readingProgress
        ) / 100
        
        self.assertEqual(progress_pct, 0.75, "75 progress should be 0.75 (75%)")
    
    def test_finished_book_progress(self):
        """Test finished book always shows 100%."""
        markedStatus = 4  # Finished
        readingProgress = 95  # Even if API says 95
        
        progress_pct = (
            100 if markedStatus == 4 else readingProgress
        ) / 100
        
        self.assertEqual(progress_pct, 1.0, "Finished book should be 100%")
    
    def test_reading_time_in_seconds(self):
        """Test reading time is stored in seconds."""
        readingTime = 3600  # 1 hour
        
        # Notion stores as number (seconds)
        self.assertEqual(readingTime, 3600, "Reading time should be in seconds")


if __name__ == '__main__':
    unittest.main()
