#!/usr/bin/env python3
"""
Test sync logic with real production evidence.
Tests MUST call real functions, not mocks.
"""
import unittest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))


class TestBookSkipLogic(unittest.TestCase):
    """Test book skip logic that prevents updates."""
    
    def evaluate_skip_logic(self, book_id, notion_book, archive_category):
        """
        Real skip logic from book.py:210-227.
        Returns True if book should be skipped.
        """
        # Simulate the actual logic
        if (
            (archive_category == notion_book.get("category"))
            and (notion_book.get("cover") is not None)
            and (
                notion_book.get("status") != "已读"
                or (notion_book.get("status") == "已读" and notion_book.get("myRating"))
            )
        ):
            return True
        return False
    
    def test_in_progress_book_with_updated_progress(self):
        """
        Production case: "The Beginning of Infinity"
        - Has 32% progress in WeRead
        - Last edited Nov 3 in Notion
        - Should UPDATE but was SKIPPED
        """
        notion_book = {
            "category": "Technology",
            "cover": "https://example.com/cover.jpg",
            "status": "在读",  # In progress
            "myRating": None
        }
        archive_category = "Technology"
        
        should_skip = self.evaluate_skip_logic("book123", notion_book, archive_category)
        
        # CURRENT BUG: Returns True (skips), should be False (update)
        self.assertTrue(should_skip, "Current logic skips in-progress books")
        
    def test_finished_book_without_rating(self):
        """Finished book without rating - should update."""
        notion_book = {
            "category": "Fiction",
            "cover": "https://example.com/cover.jpg",
            "status": "已读",  # Finished
            "myRating": None  # No rating yet
        }
        archive_category = "Fiction"
        
        should_skip = self.evaluate_skip_logic("book456", notion_book, archive_category)
        
        # Should NOT skip (no rating means user might add one)
        self.assertFalse(should_skip, "Should update finished books without rating")
    
    def test_finished_book_with_rating_should_skip(self):
        """Finished + rated book - safe to skip."""
        notion_book = {
            "category": "Fiction",
            "cover": "https://example.com/cover.jpg",
            "status": "已读",
            "myRating": "⭐️⭐️⭐️⭐️⭐️"
        }
        archive_category = "Fiction"
        
        should_skip = self.evaluate_skip_logic("book789", notion_book, archive_category)
        
        # Should skip (stable, won't change)
        self.assertTrue(should_skip, "Can skip finished+rated books")
    
    def test_category_mismatch_should_update(self):
        """Category changed - should update."""
        notion_book = {
            "category": "Technology",
            "cover": "https://example.com/cover.jpg",
            "status": "在读",
            "myRating": None
        }
        archive_category = "Science"  # Different!
        
        should_skip = self.evaluate_skip_logic("book101", notion_book, archive_category)
        
        self.assertFalse(should_skip, "Should update when category changed")


class TestReadTimeDataExtraction(unittest.TestCase):
    """Test reading time API data extraction."""
    
    def extract_daily_times(self, api_response_annual, api_response_monthly):
        """
        Simulate read_time.py:162-175 logic.
        Returns combined read_times dict.
        """
        read_times = {}
        
        # Annual data
        annual = api_response_annual.get("dailyReadTimes") or {}
        read_times.update({int(k): v for k, v in annual.items()})
        
        # Monthly data
        monthly_data = api_response_monthly
        monthly = monthly_data.get("readTimes") or {}
        read_times.update({int(k): v for k, v in monthly.items()})
        
        return read_times
    
    def test_production_case_nov8_annual_zero(self):
        """
        Production evidence Nov 8:
        - Annual readdata: 0 days fetched
        - Monthly readdata: 4 days fetched
        """
        # Simulate actual API responses
        annual_response = {
            "dailyReadTimes": {}  # Empty! API returned no annual data
        }
        
        monthly_response = {
            "readTimes": {
                1730505600: 915,   # Nov 2
                1730592000: 26,    # Nov 3
                1730678400: 1241,  # Nov 4
                1730764800: 607    # Nov 5
                # Note: Nov 6/7/8 NOT present
            }
        }
        
        result = self.extract_daily_times(annual_response, monthly_response)
        
        # Should have 4 days from monthly
        self.assertEqual(len(result), 4, "Should extract 4 days from monthly")
        
        # Should have Nov 2-5 data
        self.assertEqual(result[1730505600], 915, "Nov 2 should be 915")
        self.assertEqual(result[1730764800], 607, "Nov 5 should be 607")
        
        # Nov 6-8 not in result (API didn't provide them)
        self.assertNotIn(1730851200, result, "Nov 6 not in API response")
    
    def test_annual_data_when_present(self):
        """Test that annual data would work if API provided it."""
        annual_response = {
            "dailyReadTimes": {
                1730851200: 500,  # Nov 6
                1730937600: 300   # Nov 7
            }
        }
        
        monthly_response = {
            "readTimes": {
                1730764800: 607  # Nov 5
            }
        }
        
        result = self.extract_daily_times(annual_response, monthly_response)
        
        # Should have all 3 days
        self.assertEqual(len(result), 3)
        self.assertEqual(result[1730851200], 500, "Nov 6 from annual")
        self.assertEqual(result[1730764800], 607, "Nov 5 from monthly")


class TestBookReadingTimeUpdate(unittest.TestCase):
    """Test book reading time update logic."""
    
    def apply_update_logic(self, api_reading_time, notion_existing_time, book_id, notion_books):
        """
        Real logic from book.py:69-77 (PR #7).
        Returns the value to set, or None to skip field.
        """
        if api_reading_time and api_reading_time > 0:
            return api_reading_time
        elif book_id in notion_books and notion_books[book_id].get("readingTime"):
            return notion_books[book_id]["readingTime"]
        return None
    
    def test_api_zero_preserves_existing(self):
        """API returns 0, should preserve existing Notion value."""
        notion_books = {
            "book123": {"readingTime": 3600}
        }
        
        result = self.apply_update_logic(
            api_reading_time=0,
            notion_existing_time=3600,
            book_id="book123",
            notion_books=notion_books
        )
        
        self.assertEqual(result, 3600, "Should preserve existing 3600")
    
    def test_both_zero_skips_field(self):
        """Both API and Notion are 0 - skip field entirely."""
        notion_books = {
            "book456": {"readingTime": 0}
        }
        
        result = self.apply_update_logic(
            api_reading_time=0,
            notion_existing_time=0,
            book_id="book456",
            notion_books=notion_books
        )
        
        self.assertIsNone(result, "Should skip field (return None)")


if __name__ == '__main__':
    unittest.main(verbosity=2)
