"""Store large historical marts compressed; materialize atomically for SQLite."""
from pathlib import Path
import gzip
import hashlib
import os
import shutil
import tempfile


def pack_snapshot(source: Path) -> Path:
    source=Path(source)
    packed=source.with_suffix(source.suffix+'.gz')
    with tempfile.NamedTemporaryFile(dir=packed.parent,delete=False) as tmp:
        temporary=Path(tmp.name)
    try:
        with source.open('rb') as inp, gzip.open(temporary,'wb',compresslevel=6) as out:
            shutil.copyfileobj(inp,out)
        os.replace(temporary,packed)
    finally:
        temporary.unlink(missing_ok=True)
    return packed


def materialize_snapshot(packed: Path) -> Path:
    packed=Path(packed)
    stat=packed.stat()
    identity=f'{packed.resolve()}:{stat.st_mtime_ns}:{stat.st_size}'
    target=Path(tempfile.gettempdir())/('export-mart-'+hashlib.sha256(identity.encode()).hexdigest()+'.sqlite')
    if target.exists():return target
    with tempfile.NamedTemporaryFile(dir=target.parent,delete=False) as tmp:
        temporary=Path(tmp.name)
    try:
        with gzip.open(packed,'rb') as inp, temporary.open('wb') as out:
            shutil.copyfileobj(inp,out)
        with temporary.open('rb') as check:
            if check.read(16)!=b'SQLite format 3\x00':raise ValueError('Invalid SQLite snapshot')
        os.replace(temporary,target)
    finally:
        temporary.unlink(missing_ok=True)
    return target


if __name__=='__main__':
    import sys
    print(pack_snapshot(Path(sys.argv[1])))
