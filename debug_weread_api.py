#!/usr/bin/env python3
"""Debug script to trace WeRead API responses."""
import os
import sys
import json

# Mock environment
os.environ['WEREAD_API_KEY'] = 'dummy'

sys.path.insert(0, 'scripts')
from weread_api import WeReadApi

# Test the normalization logic with mock responses
print("=" * 70)
print("TESTING get_read_info NORMALIZATION")
print("=" * 70)

api = WeReadApi.__new__(WeReadApi)

# Test case 1: API returns nested structure with actual values
print("\n[Test 1] Nested structure with values")
mock_nested = {
    "book": {
        "progress": 75,
        "recordReadingTime": 3600,
        "finishTime": None,
        "updateTime": 1699000000
    }
}

book = mock_nested.get("book") or mock_nested
progress = book.get("progress", 0) or 0
reading_time = book.get("recordReadingTime", 0) or 0

print(f"Input: {json.dumps(mock_nested, indent=2)}")
print(f"Extracted - progress: {progress}, reading_time: {reading_time}")
assert progress == 75 and reading_time == 3600, "Failed!"
print("✓ PASS")

# Test case 2: API returns flat structure with actual values
print("\n[Test 2] Flat structure with values")
mock_flat = {
    "progress": 85,
    "recordReadingTime": 7200,
    "finishTime": None,
    "updateTime": 1699100000
}

book = mock_flat.get("book") or mock_flat
progress = book.get("progress", 0) or 0
reading_time = book.get("recordReadingTime", 0) or 0

print(f"Input: {json.dumps(mock_flat, indent=2)}")
print(f"Extracted - progress: {progress}, reading_time: {reading_time}")
assert progress == 85 and reading_time == 7200, "Failed!"
print("✓ PASS")

# Test case 3: API returns 0 values (ACTUAL PRODUCTION CASE)
print("\n[Test 3] API returns explicit zeros (production symptom)")
mock_zeros = {
    "progress": 0,
    "recordReadingTime": 0,
    "finishTime": None,
    "updateTime": 1699200000
}

book = mock_zeros.get("book") or mock_zeros
progress = book.get("progress", 0) or 0
reading_time = book.get("recordReadingTime", 0) or 0

print(f"Input: {json.dumps(mock_zeros, indent=2)}")
print(f"Extracted - progress: {progress}, reading_time: {reading_time}")
print(f"⚠️  ISSUE: Cannot distinguish between 'API returned 0' vs 'API missing data'")
print(f"⚠️  Current code treats both as 0 and OVERWRITES existing Notion values!")
print("✓ Logic works, but produces wrong result for this case")

# Test case 4: API returns None values
print("\n[Test 4] API returns None (missing data)")
mock_none = {
    "progress": None,
    "recordReadingTime": None,
    "finishTime": None,
}

book = mock_none.get("book") or mock_none
progress = book.get("progress", 0) or 0
reading_time = book.get("recordReadingTime", 0) or 0

print(f"Input: {json.dumps(mock_none, indent=2)}")
print(f"Extracted - progress: {progress}, reading_time: {reading_time}")
print(f"⚠️  ISSUE: None converted to 0, OVERWRITES existing Notion values!")
print("✓ Logic works, but produces wrong result for this case")

# Test case 5: API missing fields entirely
print("\n[Test 5] API missing fields")
mock_missing = {
    "finishTime": None,
    "updateTime": 1699300000
}

book = mock_missing.get("book") or mock_missing
progress = book.get("progress", 0) or 0
reading_time = book.get("recordReadingTime", 0) or 0

print(f"Input: {json.dumps(mock_missing, indent=2)}")
print(f"Extracted - progress: {progress}, reading_time: {reading_time}")
print(f"⚠️  ISSUE: Missing fields default to 0, OVERWRITES existing Notion values!")
print("✓ Logic works, but produces wrong result for this case")

print("\n" + "=" * 70)
print("ROOT CAUSE HYPOTHESIS")
print("=" * 70)
print("""
The PR #6 fix correctly handles nested vs flat API responses.
However, it does NOT protect existing Notion data when WeRead API returns:
- Explicit zeros (progress=0, recordReadingTime=0)
- None values
- Missing fields

Current flow:
1. get_read_info() extracts progress/time with `or 0` fallback
2. book.py line 69: book["阅读时长"] = book.get("readingTime")
3. If readingTime is 0, Notion field is updated to 0
4. Existing non-zero Notion values are OVERWRITTEN

Evidence from production:
- 315/494 books have duration=0
- Some have progress>0 but duration=0 (e.g., 32% progress, 0 duration)
- This suggests WeRead API either:
  a) Does not provide per-book reading time via /book/getprogress
  b) Returns 0 for books without recent activity
  c) Returns data in a different structure/field

REQUIRED FIXES:
1. Verify what /book/getprogress ACTUALLY returns (check gateway docs/real response)
2. If API doesn't provide duration: DO NOT update that field in Notion
3. Distinguish None/missing (skip update) from genuine 0 (book not started)
4. Add read-only mode to observe actual API responses without Notion writes
""")
