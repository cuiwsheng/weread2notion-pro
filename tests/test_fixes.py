#!/usr/bin/env python3
"""
Evidence-based regression tests for production issues.
Tests based on actual Notion DB state and GitHub Actions logs.
"""
import unittest
import os


class TestHeatmapBranchURL(unittest.TestCase):
    """Test heatmap branch URL parsing (Issue #1)."""
    
    def parse_branch_from_ref(self, ref):
        """Simulate the fixed parsing logic."""
        if ref.startswith('refs/heads/'):
            return '/'.join(ref.split('/')[2:])
        return ref
    
    def test_main_branch(self):
        """Test main branch parsing."""
        ref = 'refs/heads/main'
        branch = self.parse_branch_from_ref(ref)
        self.assertEqual(branch, 'main')
    
    def test_simple_feature_branch(self):
        """Test simple feature branch."""
        ref = 'refs/heads/feature-xyz'
        branch = self.parse_branch_from_ref(ref)
        self.assertEqual(branch, 'feature-xyz')
    
    def test_nested_branch_with_slash(self):
        """Test branch with slash prefix (production bug case)."""
        ref = 'refs/heads/cursor/fix-reading-progress-time-sync-b834'
        branch = self.parse_branch_from_ref(ref)
        # OLD BUG: .split('/')[-1] returns 'fix-reading-progress-time-sync-b834'
        # NEW FIX: Should return 'cursor/fix-reading-progress-time-sync-b834'
        self.assertEqual(branch, 'cursor/fix-reading-progress-time-sync-b834')
    
    def test_deeply_nested_branch(self):
        """Test branch with multiple slashes."""
        ref = 'refs/heads/feature/subfeature/fix-xyz'
        branch = self.parse_branch_from_ref(ref)
        self.assertEqual(branch, 'feature/subfeature/fix-xyz')
    
    def test_already_parsed_branch(self):
        """Test branch name without refs/heads prefix."""
        ref = 'main'
        branch = self.parse_branch_from_ref(ref)
        self.assertEqual(branch, 'main')
    
    def test_production_url_construction(self):
        """Test actual URL construction that caused 404."""
        repo = 'cuiwsheng/weread2notion-pro'
        ref = 'refs/heads/cursor/fix-reading-progress-time-sync-b834'
        image_file = '8c331d99-8cf0-49a9-9c12-46a5643e579d.svg'
        
        # Correct parsing
        branch = self.parse_branch_from_ref(ref)
        correct_url = f"https://raw.githubusercontent.com/{repo}/{branch}/OUT_FOLDER/{image_file}"
        
        # Verify URL contains correct branch
        self.assertIn('cursor/fix-reading-progress-time-sync-b834', correct_url)
        self.assertNotIn('refs/heads', correct_url)
        
        # OLD BUG would produce:
        old_branch = ref.split('/')[-1]  # Wrong: 'fix-reading-progress-time-sync-b834'
        wrong_url = f"https://raw.githubusercontent.com/{repo}/{old_branch}/OUT_FOLDER/{image_file}"
        
        # Verify the bug
        self.assertNotIn('cursor/', wrong_url)
        self.assertNotEqual(correct_url, wrong_url)


class TestBookReadingTimePreservation(unittest.TestCase):
    """Test preservation of existing Notion reading time values (Issue #2)."""
    
    def apply_reading_time_logic(self, api_reading_time, existing_notion_time):
        """Simulate the fixed book reading time logic."""
        # New logic: Only update if API provides valid data
        if api_reading_time and api_reading_time > 0:
            return api_reading_time
        elif existing_notion_time:
            # Preserve existing non-zero value
            return existing_notion_time
        return None  # Don't set field if no valid data
    
    def test_api_provides_valid_time(self):
        """API returns positive reading time - should update."""
        result = self.apply_reading_time_logic(
            api_reading_time=3600,
            existing_notion_time=1800
        )
        self.assertEqual(result, 3600, "Should update to new API value")
    
    def test_api_returns_zero_preserve_existing(self):
        """API returns 0, Notion has existing value - should preserve."""
        result = self.apply_reading_time_logic(
            api_reading_time=0,
            existing_notion_time=3600
        )
        self.assertEqual(result, 3600, "Should preserve existing Notion value")
    
    def test_api_returns_none_preserve_existing(self):
        """API returns None, Notion has existing value - should preserve."""
        result = self.apply_reading_time_logic(
            api_reading_time=None,
            existing_notion_time=3600
        )
        self.assertEqual(result, 3600, "Should preserve existing Notion value")
    
    def test_both_zero_no_update(self):
        """Both API and Notion are 0/None - don't update field."""
        result = self.apply_reading_time_logic(
            api_reading_time=0,
            existing_notion_time=None
        )
        self.assertIsNone(result, "Should not update field")
    
    def test_production_case_32_percent_progress_zero_duration(self):
        """
        Production case: "The Beginning of Infinity"
        - Progress: 32% (from API)
        - Duration: 0 (API doesn't provide it)
        - Existing Notion duration: 0 (was overwritten by previous bug)
        
        With fix: Duration should remain 0 (not overwrite with 0 again)
        Future runs: If user reads more, duration might appear
        """
        # Simulate: API returns progress but no duration
        api_reading_time = 0
        existing_notion_time = 0
        
        result = self.apply_reading_time_logic(api_reading_time, existing_notion_time)
        
        # Should not update (None means skip this field)
        self.assertIsNone(result, "Should skip updating when both are 0")


class TestAPIResponseNormalization(unittest.TestCase):
    """Test API response normalization from PR #6 (still valid)."""
    
    def normalize_api_response(self, data):
        """Simulate get_read_info normalization logic."""
        book = data.get("book") or data
        progress = book.get("progress", 0) or 0
        reading_time = book.get("recordReadingTime", 0) or 0
        return {"progress": progress, "reading_time": reading_time}
    
    def test_nested_structure(self):
        """API returns nested {book: {...}} structure."""
        data = {
            "book": {
                "progress": 75,
                "recordReadingTime": 3600
            }
        }
        result = self.normalize_api_response(data)
        self.assertEqual(result["progress"], 75)
        self.assertEqual(result["reading_time"], 3600)
    
    def test_flat_structure(self):
        """API returns flat {progress: ...} structure (PR #6 bug case)."""
        data = {
            "progress": 85,
            "recordReadingTime": 7200
        }
        result = self.normalize_api_response(data)
        self.assertEqual(result["progress"], 85)
        self.assertEqual(result["reading_time"], 7200)
    
    def test_api_returns_zero_not_none(self):
        """API explicitly returns 0 (common case in production)."""
        data = {
            "progress": 32,  # Has progress
            "recordReadingTime": 0  # But no duration
        }
        result = self.normalize_api_response(data)
        self.assertEqual(result["progress"], 32)
        self.assertEqual(result["reading_time"], 0)
        # Note: This is valid extraction - the issue is what we do with 0


if __name__ == '__main__':
    # Run tests with verbose output
    unittest.main(verbosity=2)
