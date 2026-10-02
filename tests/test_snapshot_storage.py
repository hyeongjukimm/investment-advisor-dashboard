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
