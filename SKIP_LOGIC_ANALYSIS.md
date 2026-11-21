# Book Skip Logic Analysis

## Current Implementation

**File**: `scripts/book.py:210-220`

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

books = list((set(notebooks) | set(books)) - set(not_need_sync))
```

## What Gets Skipped

A book is **skipped** (not synced) if ALL these conditions are true:

1. **Same category**: `archive_dict.get(key) == value.get("category")`
   - Book's WeRead archive category matches Notion database category
   
2. **Has cover**: `value.get("cover") is not None`
   - Notion already has a cover image
   
3. **Either**:
   - **Not finished**: `value.get("status") != "已读"`
   - **Finished with rating**: `value.get("status") == "已读" and value.get("myRating")`

## Problem: Aggressive Skipping

### Observed Behavior

From production logs (weread run 42437585846):
- **Only Notion GET/query operations**
- **NO PATCH/create operations**
- Suggests most/all books were skipped

### Issue

Books are skipped even when:
- ✅ Reading progress changed (e.g., 30% → 35%)
- ✅ Reading time increased (if API provided it)
- ✅ Last reading date updated
- ✅ Notes/bookmarks added (handled by weread.py, separate workflow)

**Impact**: Actively reading books may not show updated progress in Notion.

## Design Intent (Inferred)

The logic seems intended to skip books where:
- Metadata is stable (category, cover set)
- Book is "settled" (unfinished but stable, or finished with rating)

**Assumption**: If category/cover/rating are set, nothing else important changed.

**Reality**: Progress and reading time change frequently for in-progress books.

## Evidence from Production

### Books NOT Updated Despite Active Reading

Based on skip conditions, a book like "The Beginning of Infinity" would be skipped if:
- It's in the same WeRead archive category as Notion
- Notion has a cover
- Status is "在读" (in progress) OR status is "已读" (finished) with a rating

**Result**: Progress updated from 30% to 32% would not sync to Notion.

### Why This Matters

Users report:
- "阅读进度没有同步" (progress not syncing)
- Book shows old progress despite continued reading

The skip logic may be a significant contributor to this symptom.

## Potential Solutions

### Option 1: Always Sync Books with Notes (Conservative)

Only skip if book is in notebooks list:
```python
if key not in notebooks:  # Has no notes/highlights
    # Apply current skip logic
```

**Rationale**: If user is taking notes, they're actively reading.

### Option 2: Track Last Update Time (Moderate)

Add `lastUpdated` field to Notion, skip only if:
- Metadata matches AND
- WeRead last update time <= Notion last update time

**Requires**: Schema change (new Notion field)

### Option 3: Remove Skip Logic (Aggressive)

Sync all books every time.

**Pros**: Guarantees freshness  
**Cons**: More API calls, slower sync

### Option 4: Skip Only Finished+Rated (Current PR #7 Approach)

```python
if (
    value.get("status") == "已读" 
    and value.get("myRating")
    and archive_dict.get(key) == value.get("category")
    and value.get("cover") is not None
):
    not_need_sync.append(key)
```

Only skip books that are:
- Definitively finished ("已读")
- Have user rating (stable, unlikely to change)
- Metadata matches

**Rationale**: Finished+rated books are truly settled, in-progress books always sync.

## Recommendation

**Implement Option 4** in a follow-up PR:
1. Less aggressive skipping
2. In-progress books always update
3. Finished books still benefit from skip optimization
4. No schema changes required

## Testing Requirements

Before implementing:
1. Add logging to show which books are skipped and why
2. Observe production run to confirm hypothesis
3. Measure performance impact of reduced skipping

## Current Status

**PR #7**: Does NOT change skip logic (out of scope)  
**This Analysis**: Documents the issue for future investigation  
**Next Step**: Add skip reason logging, observe production behavior
