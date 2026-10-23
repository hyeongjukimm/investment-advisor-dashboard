"""Store large historical marts compressed; materialize atomically for SQLite."""
from pathlib import Path
import gzip
import json
import hashlib
import os
import shutil
import tempfile


MAX_PART_BYTES = 48 * 1024 * 1024

def pack_snapshot(source: Path) -> Path:
    source=Path(source)
    packed=source.with_suffix(source.suffix+'.gz')
    with tempfile.NamedTemporaryFile(dir=packed.parent,delete=False) as tmp:
        temporary=Path(tmp.name)
    try:
        with source.open('rb') as inp, gzip.open(temporary,'wb',compresslevel=6) as out:
            shutil.copyfileobj(inp,out)
        if temporary.stat().st_size > MAX_PART_BYTES:
            parts = []
            with temporary.open('rb') as inp:
                while chunk := inp.read(MAX_PART_BYTES):
                    digest = hashlib.sha256(chunk).hexdigest()
                    name = packed.name + '.part-' + digest
                    (packed.parent / name).write_bytes(chunk)
                    parts.append({'name': name, 'sha256': digest})
            temporary.write_text(json.dumps({'format': 'sqlite-gzip-parts-v1', 'parts': parts}))
            os.replace(temporary, packed)
            keep = {part['name'] for part in parts}
        else:
            os.replace(temporary, packed)
            keep = set()
        for old in packed.parent.glob(packed.name + '.part-*'):
            if old.name not in keep:
                old.unlink()
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
        with packed.open('rb') as probe:
            multipart = probe.read(1) == b'{' 
        if multipart:
            manifest = json.loads(packed.read_text())
            if manifest.get('format') != 'sqlite-gzip-parts-v1':
                raise ValueError('Invalid snapshot manifest')
            with tempfile.TemporaryFile() as combined:
                for part in manifest['parts']:
                    name = part['name']
                    if Path(name).name != name:
                        raise ValueError('Invalid snapshot part path')
                    content = (packed.parent / name).read_bytes()
                    if hashlib.sha256(content).hexdigest() != part['sha256']:
                        raise ValueError('Corrupt snapshot part')
                    combined.write(content)
                combined.seek(0)
                with gzip.GzipFile(fileobj=combined, mode='rb') as inp, temporary.open('wb') as out:
                    shutil.copyfileobj(inp, out)
        else:
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
