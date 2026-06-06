# FileMind Backup & Version Strategy

**Created:** 2026-04-08  
**Version:** 1.0

---

## PRINCIPLES

1. **Backup before every destructive/config-changing operation**
2. **Version-tag all code changes** (date + short description)
3. **Index is the most valuable asset** — protect it first
4. **Vault is the canonical backup location** — timestamped snapshots
5. **Git for code, robocopy for data** — right tool for each job

---

## WHAT TO BACKUP

| Asset | Location | Backup To | Frequency |
|---|---|---|---|
| **Index (SQLite)** | `C:\AI_STATION\.index\filemind.db` | `vault\backups\index_<timestamp>\` | Before every scan |
| **Index (Qdrant)** | `C:\AI_STATION\.index\qdrant\` | `vault\backups\qdrant_<timestamp>\` | Before every scan |
| **Code** | `C:\AI_STATION\filemind\*.py` | `vault\backups\code_<timestamp>\` | Before config changes |
| **Docs** | `C:\AI_STATION\filemind\docs\*.md` | `vault\backups\docs_<timestamp>\` | After every session |
| **Config** | `C:\AI_STATION\.env`, `config.py` | `vault\backups\config_<timestamp>\` | Before every change |
| **Session extracts** | `docs\SESSION_LEARNING_*` | `vault\backups\docs_<timestamp>\` | End of every session |

---

## BACKUP NAMING CONVENTION

```
{asset}_{YYYYMMDD}_{HHMMSS}
```

Examples:
- `index_20260408_103500`
- `code_20260408_104500`
- `docs_20260408_110000`

---

## AUTOMATED BACKUP CHECKPOINTS

### 1. Pre-Scan Backup (automatic)
Before every `python run.py scan --full`:
```
robocopy "C:\AI_STATION\.index" "C:\AI_STATION\vault\backups\index_YYYYMMDD_HHMMSS" /E /NFL /NDL /NJH /NJS
```

### 2. Pre-Config-Change Backup (manual trigger)
Before changing `config.py`:
```
robocopy "C:\AI_STATION\filemind" "C:\AI_STATION\vault\backups\code_YYYYMMDD_HHMMSS" *.py *.toml /NFL /NDL /NJH /NJS /NC /NS /NP
```

### 3. Post-Session Backup (automatic at session end)
```
robocopy "C:\AI_STATION\filemind\docs" "C:\AI_STATION\vault\backups\docs_YYYYMMDD_HHMMSS" *.md /NFL /NDL /NJH /NJS /NC /NS /NP
```

### 4. Major Milestone Backup
Before running untested changes:
```
Full index + code + config → vault\backups\milestone_YYYYMMDD_{description}
```

---

## CURRENT BACKUP STATE (2026-04-08)

| Backup | Timestamp | Status |
|---|---|---|
| `index_backup_20260408_103500` | 10:35 AM | ✅ Pre-audit baseline |
| `docs_backup_20260408_103500` | 10:35 AM | ✅ Pre-audit baseline |
| `filemind_code_backup_20260408_103500` | 10:35 AM | ✅ Pre-audit baseline |
| `index_20260408_104900` | 10:49 AM | ✅ Pre-config-change |
| `index_20260408_110000` | 11:00 AM | ✅ Post-fixes (batch embedding) |

---

## RETENTION POLICY

| Backup Type | Keep | Delete After |
|---|---|---|
| Pre-scan backups | Last 3 | 7 days |
| Config change backups | Last 5 | 14 days |
| Session docs backups | All | 30 days |
| Milestone backups | All | Never (archive instead) |

**Cleanup script** (run weekly):
```powershell
# Delete index backups older than 7 days
Get-ChildItem "C:\AI_STATION\vault\backups\index_*" | Where-Object { $_.CreationTime -lt (Get-Date).AddDays(-7) } | Remove-Item -Recurse
```

---

## VERSION CONTROL FOR CODE

### Git Strategy (if/when repo is initialized)
```
# Before each change:
git add -A
git commit -m "feat/fix: description [YYYY-MM-DD]"
git tag v{date}  # e.g., v20260408

# After major fix:
git tag v{date}-batch-embedding
```

### Without Git (current state)
- Use robocopy to `vault\backups\code_YYYYMMDD_HHMMSS`
- Name the snapshot after the change: `code_20260408_batch_embedding_fix`

---

## RECOVERY PROCEDURES

### Recover Index
```
robocopy "C:\AI_STATION\vault\backups\index_YYYYMMDD_HHMMSS" "C:\AI_STATION\.index" /E /NFL /NDL /NJH /NJS
```

### Recover Code
```
robocopy "C:\AI_STATION\vault\backups\code_YYYYMMDD_HHMMSS" "C:\AI_STATION\filemind" *.py /NFL /NDL /NJH /NJS
```

### Recover Docs
```
robocopy "C:\AI_STATION\vault\backups\docs_YYYYMMDD_HHMMSS" "C:\AI_STATION\filemind\docs" *.md /NFL /NDL /NJH /NJS
```

---

## SAFETY RULES

1. **Never modify config.py without a backup first**
2. **Never run scan --full without index backup first**
3. **Never delete from index without verifying file is gone from disk** (now automated)
4. **Mass deletion cap: 100 files triggers warning** (now automated)
5. **Verify backup succeeded before proceeding** (check file count matches)
6. **At session end: copy session extract + this doc to vault**

---

## SESSION BACKUP CHECKLIST (End of Every Session)

- [ ] Copy session learning extract to `vault\backups\docs_YYYYMMDD`
- [ ] Copy updated LOCAL_MODEL_REGISTRY.md
- [ ] Copy updated FILEMIND_V2_UPGRADE_PLAN.md
- [ ] Copy updated AGENT_PLAYBOOK.md
- [ ] Run `python run.py stats` and save output
- [ ] Note current index size, chunk count, file count
- [ ] If config changed: backup code
- [ ] If scan ran: backup index

---

*This document is versioned. Update after every session that changes backup strategy.*
