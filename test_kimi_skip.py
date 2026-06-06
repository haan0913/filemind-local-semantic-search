import os
from pathlib import Path
from config import config
from scanner import FileScanner

scanner = FileScanner()
kimi_root = Path("C:/Users/amirk/.kimi")

included = []
excluded = []
skipped_dirs = []

for dirpath, dirnames, filenames in os.walk(str(kimi_root)):
    before = list(dirnames)
    
    # Remove symlinks/junctions first
    for d in list(dirnames):
        full_dir = os.path.join(dirpath, d)
        if os.path.islink(full_dir) or os.path.isjunction(full_dir):
            dirnames.remove(d)
            skipped_dirs.append((os.path.join(dirpath, d), dirpath, "symlink/junction"))
    
    # Then apply skip rules
    for d in list(dirnames):
        if scanner._should_skip_dir(d) or scanner._should_skip_subdir(d, dirpath):
            dirnames.remove(d)
            skipped_dirs.append((os.path.join(dirpath, d), dirpath, "skip_rule"))
    
    for fn in filenames:
        ext = os.path.splitext(fn)[1].lower()
        fp = os.path.join(dirpath, fn)
        rel = os.path.relpath(fp, str(kimi_root)).replace("\\", "/")
        if ext in config.index_extensions and scanner._should_include_file(rel):
            included.append(rel)
        else:
            excluded.append(rel)
    
    if len(included) + len(excluded) > 5000:
        print("... stopping at 5000 files", flush=True)
        break

print(f"INCLUDED from .kimi: {len(included)}")
print(f"EXCLUDED from .kimi: {len(excluded)}")
print(f"SKIPPED dirs: {len(skipped_dirs)}")
print()
print("Sample included:")
for f in sorted(included)[:25]:
    print(f"  + {f}")
print()
print("Sample excluded:")
for f in sorted(excluded)[:15]:
    print(f"  - {f}")
print()
print("Skipped dirs:")
for s, p, reason in skipped_dirs[:15]:
    rel_s = os.path.relpath(s, str(kimi_root)).replace("\\", "/")
    print(f"  x {rel_s} ({reason})")
