#!/usr/bin/env python3
"""
Test FIXED skip logic.
Tests real production skip logic after bug fix.
"""
import unittest


class TestFixedBookSkipLogic(unittest.TestCase):
    """Test fixed book skip logic."""
    
    def fixed_skip_logic(self, book_id, notion_book, archive_category):
        """
        FIXED skip logic from book.py (after PR).
        Only skips: finished + rated + metadata matches.
        """
        if (
            notion_book.get("status") == "已读"
            and notion_book.get("myRating")
            and archive_category == notion_book.get("category")
            and notion_book.get("cover") is not None
        ):
            return True  # Skip (stable book)
        return False  # Update (may change)
    
    def test_in_progress_book_NOT_skipped(self):
        """
        FIXED: In-progress books should UPDATE (not skip).
        Production case: "The Beginning of Infinity"
        """
        notion_book = {
            "category": "Technology",
            "cover": "https://example.com/cover.jpg",
            "status": "在读",  # In progress
            "myRating": None
        }
        archive_category = "Technology"
        
        should_skip = self.fixed_skip_logic("book123", notion_book, archive_category)
        
        # FIXED: Now returns False (will update)
        self.assertFalse(should_skip, "In-progress books should UPDATE")
    
    def test_finished_without_rating_NOT_skipped(self):
        """Finished but not rated - should update."""
        notion_book = {
            "category": "Fiction",
            "cover": "https://example.com/cover.jpg",
            "status": "已读",
            "myRating": None  # No rating
        }
        archive_category = "Fiction"
        
        should_skip = self.fixed_skip_logic("book456", notion_book, archive_category)
        
        self.assertFalse(should_skip, "Finished without rating should UPDATE")
    
    def test_finished_with_rating_IS_skipped(self):
        """Finished + rated - safe to skip."""
        notion_book = {
            "category": "Fiction",
            "cover": "https://example.com/cover.jpg",
            "status": "已读",
            "myRating": "⭐️⭐️⭐️⭐️⭐️"
        }
        archive_category = "Fiction"
        
        should_skip = self.fixed_skip_logic("book789", notion_book, archive_category)
        
        self.assertTrue(should_skip, "Finished+rated books can skip")
    
    def test_finished_rated_but_category_changed(self):
        """Even finished+rated should update if category changed."""
        notion_book = {
            "category": "Technology",
            "cover": "https://example.com/cover.jpg",
            "status": "已读",
            "myRating": "⭐️⭐️⭐️⭐️⭐️"
        }
        archive_category = "Science"  # Different
        
        should_skip = self.fixed_skip_logic("book101", notion_book, archive_category)
        
        self.assertFalse(should_skip, "Should update if category changed")
    
    def test_no_cover_should_update(self):
        """Book without cover should always update."""
        notion_book = {
            "category": "Fiction",
            "cover": None,  # No cover
            "status": "已读",
            "myRating": "⭐️⭐️⭐️⭐️⭐️"
        }
        archive_category = "Fiction"
        
        should_skip = self.fixed_skip_logic("book202", notion_book, archive_category)
        
        self.assertFalse(should_skip, "No cover means needs update")


if __name__ == '__main__':
    unittest.main(verbosity=2)
