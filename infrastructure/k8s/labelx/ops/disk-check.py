"""Fail a visible, bounded operational Job before shared-volume disk exhaustion."""
import os
import shutil

for path in ('/data', '/backups'):
    disk = shutil.disk_usage(path)
    used = disk.used / disk.total
    print(f'Disk {path}: {used:.1%} used; {disk.free/1024**3:.1f} GiB free')
    if used >= .85 or disk.free < 8 * 1024**3:
        raise SystemExit('BLOCKED disk >=85% or <8 GiB free; pause ingestion and investigate')
    if used >= .75:
        print('WARNING disk >=75%; expand/move data before exhaustion')
print('PASS disk thresholds only; not disaster recovery or capacity acceptance')
