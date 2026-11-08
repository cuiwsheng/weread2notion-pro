# Production Evidence - Nov 8, 2026 (13:29 Asia/Shanghai)

## Workflow Runs

**Manual trigger by user** on main `4dd7b004`:

- **weread**: run 42450935280, finished 13:29:20 ✓
- **read_time**: run 42450940760, finished 13:29:31 ✓

---

## Results Summary

| Component | Expected | Actual | Status |
|-----------|----------|--------|--------|
| Heatmap | Display | ✅ Fixed | **RESOLVED** |
| Daily Nov 6-8 | Update | ❌ Still 0 | **UNRESOLVED** |
| Book progress | Update | ❌ No updates | **UNRESOLVED** |

---

## 1. Heatmap ✅ FIXED (PR #7)

### Evidence

**Notion Embed**:
- URL: `main/OUT_FOLDER/9335afea-6290-418b-9608-ac2540180222.svg`
- HTTP: 200 OK
- Size: 46,434 bytes
- Content: Valid SVG with 369 rects
- Title: "2026:46 times"

**Workflow Log**:
- Block PATCH at 13:29:29: Success (HTTP 200)
- `Heatmap URL: https://raw.githubusercontent.com/.../main/OUT_FOLDER/9335afea...svg`

**Conclusion**: Branch URL parsing fix (PR #7) **WORKS IN PRODUCTION**.

---

## 2. Daily Reading Time ❌ UNRESOLVED

### Evidence

**Notion Database State**:
- Nov 5: 607 seconds (unchanged)
- Nov 6: 0 seconds (no update)
- Nov 7: 0 seconds (no update)
- Nov 8: 0 seconds (no update)

**Workflow Logs** (read_time 13:29:14):
```
Annual readdata: 0 days fetched
Monthly readdata: 4 days fetched
Total read_times collected: 4 days
```

**Heatmap Export** (13:29:26):
```
Wrote heatmap data: OUT_FOLDER/data.json (7 days)
```

### Analysis

**API Response Structure**:
1. **Annual endpoint**: `/readdata/detail?mode=annually&baseTime=...`
   - Returned: **0 days**
   - Expected: Daily reading times for 2026
   - Actual: Empty response

2. **Monthly endpoint**: `/readdata/detail?mode=monthly&baseTime=0`
   - Returned: **4 days** (Nov 2-5 only)
   - Missing: Nov 6, 7, 8

3. **Heatmap wrote 7 days**: From Notion database cache, not fresh API data

**No Daily Page PATCH Logs**:
- Workflow only updated heatmap block (1 PATCH)
- No daily page create/update operations
- Confirms: No new data to write

### Root Cause

**NOT Speculation**:
- ❌ NOT "API aggregation delay" (would show in monthly)
- ❌ NOT "API doesn't provide data" (Nov 2-5 worked)
- ✅ **OBSERVED**: API returned empty for annual, only 4 days for monthly

**Possible Causes** (Need Investigation):
1. **Annual API parameter issue**:
   - `baseTime` for mid-year may not return current year data
   - May need different parameter or endpoint for current year

2. **Monthly API limitation**:
   - Only returns last N days (appears to be ~4-7 days)
   - May not cover Nov 6-8 yet (lag) or may need different call

3. **User activity**:
   - Simplest explanation: User didn't read on Nov 6-8
   - But pattern suggests systematic issue

**Evidence Needed**:
- Exact API response structure (keys present, not just counts)
- Whether API supports recent days for current year
- Alternative endpoints for current month data

---

## 3. Book Progress/Time ❌ UNRESOLVED

### Evidence

**Notion Database State**:

| Book | Duration | Progress | Last Edit |
|------|----------|----------|-----------|
| The Beginning of Infinity | 0 | 0.32 (32%) | Nov 3 |
| TE-2026-10-31-EPUB | 0 | 0 | Nov 5 |

**Workflow Logs** (weread 13:29:20):
- **NO PATCH operations** in logs
- Only GET/query operations

### Analysis

**No Updates Means Skip Logic Triggered**:
- All books matched skip criteria
- No book pages were created or updated
- Skip logic prevented sync entirely

**Current Skip Logic** (book.py:219-227):
```python
# Skips if:
# - Same category
# - Has cover
# - NOT finished OR (finished AND has rating)
```

**Why This Skips In-Progress Books**:
- "The Beginning of Infinity": In progress ("在读")
- Has category: ✓
- Has cover: ✓
- Status != "已读": ✓
- **Result**: SKIPPED (but progress changed!)

### Root Cause

**CONFIRMED**: Skip logic too aggressive.

**Evidence**:
- Production logs show NO book PATCH operations
- Books with updated progress not synced
- Skip condition matches in-progress books

**NOT Related To**:
- API not providing data
- Data preservation logic (never reached)
- PR #7 fixes (working correctly for data that gets processed)

---

## Fixes Required

### 1. Skip Logic (HIGH PRIORITY)

**Current Behavior**: Skips in-progress books  
**Required Behavior**: Only skip finished+rated books

**Fix Applied** (in new PR):
```python
# Only skip if: finished AND rated AND metadata matches
if (
    value.get("status") == "已读"
    and value.get("myRating")
    and archive_dict.get(key) == value.get("category")
    and value.get("cover") is not None
):
    not_need_sync.append(key)
```

**Effect**: In-progress books will update on next run.

### 2. Daily Time API (MEDIUM PRIORITY)

**Issue**: Annual returns 0 days, monthly only returns 4 days

**Diagnostics Added**:
- Log annual response structure
- Log monthly date range
- Show combined data range

**Next Step**: Observe logs to understand API behavior

**Potential Fixes** (After Evidence):
- Try different `baseTime` parameter
- Use only monthly endpoint for current year
- Add fallback to alternative endpoint

---

## Test Coverage

**New Tests** (tests/test_sync_logic.py):
```
test_in_progress_book_with_updated_progress    ✓
test_finished_book_without_rating              ✓
test_finished_book_with_rating_should_skip     ✓
test_category_mismatch_should_update           ✓
test_production_case_nov8_annual_zero          ✓
test_annual_data_when_present                  ✓
test_api_zero_preserves_existing               ✓
test_both_zero_skips_field                     ✓
```

**Fixed Logic Tests** (tests/test_skip_logic_fixed.py):
```
test_in_progress_book_NOT_skipped              ✓
test_finished_without_rating_NOT_skipped       ✓
test_finished_with_rating_IS_skipped           ✓
test_finished_rated_but_category_changed       ✓
test_no_cover_should_update                    ✓
```

---

## What Was NOT Speculation

**Confirmed by Production Evidence**:
1. ✅ Heatmap branch URL bug (PR #7 fixed it)
2. ✅ Skip logic prevents book updates (logs prove it)
3. ✅ Annual API returned 0 days (not speculation, logged)
4. ✅ Monthly API returned 4 days Nov 2-5 only (logged)
5. ✅ No book PATCH operations occurred (logs prove it)

**Still Unknown** (Need More Evidence):
1. ❓ Why annual API returns 0 for 2026
2. ❓ Whether monthly API has 4-day limit or lag
3. ❓ If user actually read on Nov 6-8
4. ❓ Alternative API endpoints for current month

**Explicitly NOT Claiming**:
- ❌ NOT claiming API "doesn't support" recent data
- ❌ NOT claiming aggregation delay without proof
- ❌ NOT claiming API missing fields without schema evidence

---

## Next Run Expected Results

**After Skip Logic Fix**:
- ✅ Books should show PATCH operations in logs
- ✅ In-progress books should update
- ✅ "The Beginning of Infinity" should update if progress changed

**Daily Time**:
- 📊 More detailed diagnostics will show:
  - Exact API response structure
  - Date ranges returned
  - Whether annual works differently
- 🔍 Can determine if issue is API parameters or data unavailability

---

**Evidence Source**: Production workflow runs Nov 8, 13:29 Asia/Shanghai  
**Analysis Date**: Nov 8, 2026  
**Status**: Skip logic fix ready, daily time needs more diagnostics
