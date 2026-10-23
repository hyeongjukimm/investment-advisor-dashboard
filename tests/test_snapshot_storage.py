import sqlite3
from snapshot_storage import pack_snapshot, materialize_snapshot


def test_compressed_snapshot_round_trip(tmp_path):
    source=tmp_path/'share.sqlite'
    with sqlite3.connect(source) as con:
        con.execute('CREATE TABLE observations (value INTEGER)')
        con.execute('INSERT INTO observations VALUES (42)')
    packed=pack_snapshot(source)
    source.unlink()
    restored=materialize_snapshot(packed)
    with sqlite3.connect(restored) as con:
        assert con.execute('SELECT value FROM observations').fetchone()[0]==42


def test_large_snapshot_parts_round_trip(tmp_path, monkeypatch):
    import snapshot_storage
    import os
    monkeypatch.setattr(snapshot_storage, 'MAX_PART_BYTES', 1024, raising=False)
    source = tmp_path / 'large.sqlite'
    with sqlite3.connect(source) as con:
        con.execute('CREATE TABLE payload (value BLOB)')
        con.execute('INSERT INTO payload VALUES (?)', (os.urandom(16384),))
    original = source.read_bytes()
    packed = pack_snapshot(source)
    parts = list(tmp_path.glob('large.sqlite.gz.part*'))
    assert len(parts) > 1
    assert all(p.stat().st_size <= 1024 for p in parts)
    source.unlink()
    assert materialize_snapshot(packed).read_bytes() == original
