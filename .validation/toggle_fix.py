from pathlib import Path
import shutil
import sys

path = Path('crates/libcontainer/src/rootfs/mount.rs')
backup = Path('/tmp/youki-sync-fixed-mount.rs')
if sys.argv[1] == 'remove':
    shutil.copyfile(path, backup)
    source = path.read_text()
    start = source.index('                    // These are superblock flags,')
    end = source.index('                    for opt in data_options', start)
    path.write_text(source[:start] + source[end:])
else:
    shutil.copyfile(backup, path)
