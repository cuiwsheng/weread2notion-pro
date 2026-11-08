# Root Cause Analysis - Reading Data Not Syncing

## Production Evidence Summary

**Date**: 2026-11-08  
**Source**: Live Notion DB inspection + GitHub Actions logs

### Symptoms
1. **Heatmap disappeared**: Embed shows 404
2. **Book reading times still 0**: 315/494 books have zero 阅读时长
3. **Daily reading times stopped**: Nov 6-8 show 0 seconds

---

## Issue #1: Heatmap 404 (CONFIRMED)

### Evidence
- Current embed URL: `https://raw.githubusercontent.com/cuiwsheng/weread2notion-pro/fix-reading-progress-time-sync-b834/OUT_FOLDER/8c331d99...svg`
- Branch name missing `cursor/` prefix
- Actual branch: `cursor/fix-reading-progress-time-sync-b834`
- Asset exists on correct branch (HTTP 200), but 404 on truncated branch name

### Root Cause
**File**: `scripts/read_time.py:141`  
**Code**:
```python
f"{os.getenv('REF', 'refs/heads/main').split('/')[-1]}/OUT_FOLDER/{image_file}"
```

**Problem**: `.split('/')[-1]` extracts only last segment:
- Input: `refs/heads/cursor/fix-reading-progress-time-sync-b834`
- Output: `fix-reading-progress-time-sync-b834` ❌
- Expected: `cursor/fix-reading-progress-time-sync-b834` ✓

**Fix**: Use `'/'.join(ref.split('/')[2:])` to extract everything after `refs/heads/`

---

## Issue #2: Book Reading Times Always 0 (PARTIALLY WRONG DIAGNOSIS IN PR #6)

### Evidence from Production
- **Book DB**: 494 books total
  - 179 have positive 阅读时长
  - 315 have zero 阅读时长
- **Examples**:
  - "TE-2026-10-31-EPUB": duration=0, progress=0, last read Nov 5
  - "The Beginning of Infinity": duration=0, progress=**32%**, last read Nov 2

### Critical Observation
**Book has 32% progress but 0 duration** - this proves:
1. Progress data IS being extracted (PR #6 fix worked for progress)
2. Duration data is NOT available from the API

### Root Cause

**WeRead API `/book/getprogress` does NOT provide per-book reading time.**

**Evidence**:
1. API endpoint name is "getprogress" not "getreadinfo"
2. Code assumes `recordReadingTime` field exists (line 92 weread_api.py)
3. Production shows most books have 0 duration despite positive progress
4. No errors in logs - API returns 0 or omits field entirely

**Historical Context**:
- PR #4 migrated from `/book/readinfo` to `/book/getprogress`
- Old endpoint may have provided `recordReadingTime`
- New endpoint does not, or provides it differently

### What PR #6 Actually Fixed
PR #6 fixed the **data extraction logic** (nested vs flat structure).  
But it CANNOT fix **missing data** from the API.

### Current Behavior (PROBLEMATIC)
```python
# weread_api.py:92
reading_time = book.get("recordReadingTime", 0) or 0
# Returns 0 if field missing/None

# book.py:69
book["阅读时长"] = book.get("readingTime")
# Updates Notion field to 0, OVERWRITING existing non-zero values
```

**Problem**: When API returns 0/None, code updates Notion to 0, erasing existing data.

### Required Fix
1. **Verify** if `/book/getprogress` actually provides `recordReadingTime`
2. **If NO**: Skip updating 阅读时长 field when data unavailable
3. **If YES**: Distinguish genuine 0 (book not started) from missing data

---

## Issue #3: Daily Reading Times Stopped (INVESTIGATION NEEDED)

### Evidence
**Daily DB** (时长 field):
- Nov 2: 915 seconds ✓
- Nov 3: 26 seconds ✓
- Nov 4: 1241 seconds ✓
- Nov 5: 607 seconds ✓
- Nov 6: **0 seconds** ❌
- Nov 7: **0 seconds** ❌
- Nov 8: **0 seconds** ❌

**Workflow Logs** (run 42437364978):
- "Wrote heatmap data: OUT_FOLDER/data.json (7 days)"
- No error messages for API calls
- Nov 5 page last edited Nov 5 (not by latest run)

### Hypotheses
1. **WeRead API returned 0 for recent days**
   - read_time.py calls `/readdata/detail` for annual + monthly data
   - API may have delay in aggregating recent reading activity

2. **Exception handling silently skipped**
   - read_time.py:166-173 has try/except that prints but continues
   - If exception occurred, would see "skipped" message (not present in logs)

3. **Data not yet available**
   - WeRead may aggregate reading time with delay
   - Nov 6-8 data genuinely 0 (user didn't read, or data not synced yet)

### Required Investigation
1. Check if API actually returns 0 or if response structure changed
2. Add detailed logging for API responses
3. Verify no silent exceptions

---

## Additional Finding: Book Skipping Logic

### Code (book.py:212-220)
```python
not_need_sync = []
for key, value in notion_books.items():
    if (
        (archive_dict.get(key) == value.get("category"))
        and (value.get("cover") is not None)
        and (
            value.get("status") != "已读"
            or (value.get("status") == "已读" and value.get("myRating"))
        )
    ):
        not_need_sync.append(key)
```

### Observation
weread workflow logs show **only Notion GET/query operations, NO PATCH/create logs**.

This suggests many/all books were skipped due to this logic. If a book matches:
- Same archive category
- Has cover
- Not finished, OR finished with rating

...it's skipped entirely, even if reading progress/time changed.

### Impact
Books that users are actively reading may not update because the skipping logic is too aggressive.

---

## Summary of Fixes Needed

### Fix 1: Heatmap Branch URL ✓ (HIGH PRIORITY)
**File**: `scripts/read_time.py:141`  
**Change**: Parse full branch name from REF, not just last segment

### Fix 2: Per-Book Reading Time (INVESTIGATION REQUIRED)
**File**: `scripts/weread_api.py:92` + `scripts/book.py:69`  
**Options**:
- A) If API provides data: Fix extraction logic
- B) If API doesn't provide data: Skip updating field (preserve existing Notion values)

### Fix 3: Daily Reading Time 0s (INVESTIGATION REQUIRED)
**File**: `scripts/read_time.py:162-173`  
**Action**: Add detailed logging to see actual API responses

### Fix 4: Book Skipping Logic (REVIEW NEEDED)
**File**: `scripts/book.py:212-220`  
**Question**: Is this logic too aggressive? Should books with changed progress/time always update?

---

## Testing Strategy

### Unit Tests (Evidence-Based)
1. REF parsing: Test various branch name formats
2. API response handling: Test 0 vs None vs missing fields
3. Notion field updates: Test preservation of existing non-zero values

### Integration Tests (Cannot Run Without Credentials)
- Actual WeRead API responses
- Notion DB state changes
- Workflow end-to-end validation

---

## Next Steps

1. ✅ Fix heatmap branch URL (definitive bug)
2. ❓ Investigate if `/book/getprogress` provides `recordReadingTime`
3. ❓ Investigate why daily times are 0 for Nov 6-8
4. ❓ Review book skipping logic aggressiveness
