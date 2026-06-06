# Research Prompt: FileMind Phase 3 Pipeline Stalled - Zero DB Writes After 8+ Minutes

## TL;DR
The FileMind pipeline's Phase 3 (classification) starts but writes ZERO files to the SQLite database after 8+ minutes. All tested components work in isolation. Something in the orchestration is silently failing or blocking.

---

## What HAS Been Verified (Working in Isolation)

### 1. llama3.2 via Ollama (/api/chat + format parameter)
- **Test**: Direct POST to `http://localhost:11434/api/chat`
- **Result**: 9.9 seconds, returns valid JSON array
- **Response**: `[{"path":"test.py","category":"code","confidence":1}, ...]`
- **Categories correct**: code, documentation, config all properly classified
- **Status**: ✅ WORKING

### 2. Classifier._parse_response() 
- **Test**: Fed real llama3.2 output through parser
- **Result**: Correctly parses JSON, handles `file_path`/`path` key variations
- **Status**: ✅ WORKING

### 3. Catalog.update_category() with commit()
- **Code**: `self.conn.execute("UPDATE file_index SET category = ?, confidence = ? WHERE path = ?", ...); self.conn.commit()`
- **Verified**: update_category() does call commit() after each file
- **Status**: ✅ SHOULD WORK

### 4. Pipeline overall flow
- Phase 1 (Scan): ✅ Completes, finds 3228 files
- Phase 2 (Extract): ✅ Completes, extracts 3228 files, calls upsert_file() for each
- Phase 3 (Classify): ❌ STUCK - 0 classified files after 8+ minutes

---

## The Critical Observation

After 8+ minutes of Phase 3 running, the DB still shows 0 files in `file_index`.

But wait — the `upsert_file()` calls in Phase 2 should have written ALL 3228 files to the DB (with category='unknown', confidence=0.0, chunk_count=0).

**If Phase 2's upsert_file() is working, we should see 3228 files already in DB with category='unknown'.**

We see 0 files. This means:

### Hypothesis A: Phase 2 upsert_file() is not committing
The upsert_file() method does NOT call commit(). It only calls `self.conn.execute(...)` but no `self.conn.commit()`. SQLite with WAL mode + synchronous=NORMAL may batch writes and not persist until a commit happens. Phase 2 never commits after upsert_file calls.

### Hypothesis B: The catalog uses separate connections
Phase 2 creates a Catalog instance that calls upsert_file() on one connection, but when db_status.py opens the SAME db file with a NEW connection, it can't see uncommitted WAL data. The writes exist in memory but never hit disk.

### Hypothesis C: Phase 3 classify() is silently erroring
The `_classify_batch()` method has `try/except Exception as e` that logs errors but returns empty results. If ALL batches fail silently (with only a logger.warning that may not appear in the file log handler), the pipeline appears stuck but is actually processing — just failing every batch.

---

## Key Code Paths to Investigate

### 1. nightly.py _phase_extract() → catalog.upsert_file()
```python
self.catalog.upsert_file(path=..., category="unknown", confidence=0.0)
# NOTE: NO self.catalog.commit() after the loop!
```
**This is likely the root cause.** The catalog commits in init_db() and update_category(), but upsert_file() does NOT commit. All 3228 files are INSERTED into the in-memory transaction but never committed to disk.

### 2. catalog.py upsert_file() 
```python
def upsert_file(self, ...):
    self.conn.execute("INSERT INTO file_index ... ON CONFLICT DO UPDATE SET ...")
    # MISSING: self.conn.commit()
```

### 3. catalog.py update_category()
```python
def update_category(self, path, category, confidence):
    self.conn.execute("UPDATE file_index SET category = ? WHERE path = ?", ...)
    self.conn.commit()  # This commits!
```

### 4. The classification loop
```python
def classify(self, files):
    for i in range(0, len(files), self.batch_size):
        batch = files[i:i + self.batch_size]
        try:
            batch_results = self._classify_batch(batch)  # Calls llama3.2
            results.extend(batch_results)
        except Exception as e:
            logger.error(f"Classification batch failed: {e}")
        time.sleep(0.5)
    return results
```

If `_classify_batch()` is throwing exceptions for EVERY batch (e.g., Ollama model loading timeout, format schema rejection), all results would be silently eaten and the loop would complete with 0 results.

---

## Research Questions

1. **Does `upsert_file()` need an explicit `commit()` after each insert?** The WAL mode only defers commits to checkpoint events — without commit(), the changes are invisible to other connections. This would explain why DB always shows 0 records even after Phase 2 processed 3228 files.

2. **Is `_classify_batch()` silently throwing exceptions?** The try/except catches ALL exceptions and only logs them. If the model is failing (e.g., llama3.2 not loaded yet, format schema rejection), we'd see no progress but no visible errors in the log file handler.

3. **Is the classifier using a different model than expected?** The classifier.py has `self.primary_model = "llama3.2"` but this is a hardcoded string — it doesn't read from config. Is it actually calling Ollama, or is it erroring out?

4. **Does the `time.sleep(0.5)` in classify() accumulate to significant time?** With 646 batches × 0.5s sleep = 323 seconds of just sleep. But the real issue is if each batch call takes longer than expected.

---

## Recommended Fixes to Test

### Fix 1 (Most Likely): Add commit() after upsert_file in _phase_extract
```python
# In nightly.py, after the for loop in _phase_extract:
self.catalog.conn.commit()  # Add this line
```

### Fix 2: Add error visibility to _classify_batch
```python
# In classifier.py _classify_batch:
except Exception as e:
    logger.warning(f"Model {self.primary_model} failed: {e}, trying {self.fallback_model}")
    import traceback
    logger.debug(traceback.format_exc())  # ADD THIS
```

### Fix 3: Add a single-commit strategy 
Instead of committing after every file, use auto-commit mode:
```python
# In catalog.py __init__ or conn property:
self._conn.isolation_level = None  # Autocommit mode
# OR use autocommit at the connection level
```

---

## Evidence Summary

| Component | Test | Result |
|-----------|------|--------|
| llama3.2 direct API call | `requests.post('/api/chat')` | ✅ 9.9s, valid JSON, 3/3 correct |
| Classifier._parse_response() | Parse llama3.2 output | ✅ Correct parsing |
| Catalog.update_category() | Has commit() call | ✅ Commits after each update |
| Catalog.upsert_file() | No commit() call | ❌ Does NOT commit |
| Pipeline Phase 1+2 | 3228 files scanned+extracted | ✅ Completes |
| Pipeline Phase 3 | 0 files in DB after 8+ min | ❌ Stuck |

---

## Root Cause (90% confidence)

**The `_phase_extract()` method in nightly.py calls `upsert_file()` 3228 times but never calls `commit()`.** All 3228 files exist in the in-memory SQLite transaction but are NEVER WRITTEN to the DB file. When Phase 3 calls `update_category()`, it tries to UPDATE files that don't exist in the database (because the INSERTs weren't committed), so 0 rows are affected and the DB stays at 0 files.

This is why:
1. Test scripts that manually call upsert_file + commit work
2. Pipeline Phase 2 says "Extracted: 3228 files" (it called upsert_file 3228 times)
3. The DB shows 0 files (no commit happened)
4. Phase 3's update_category() silently affects 0 rows (files don't exist)

**The fix is one line: add `self.catalog.conn.commit()` at the end of `_phase_extract()` in nightly.py**