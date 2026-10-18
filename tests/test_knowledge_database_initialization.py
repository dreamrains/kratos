"""Real SQLite initialization reuse; no store, transaction or fsync bypass."""
from concurrent.futures import ThreadPoolExecutor
import sqlite3
import pytest
from data_agent.knowledge.sqlite_store import KnowledgeDatabase


def _count_migrations(monkeypatch):
    calls=[];original=KnowledgeDatabase._migrate
    def migrate(self,conn):calls.append(self.path);return original(self,conn)
    monkeypatch.setattr(KnowledgeDatabase,'_migrate',migrate)
    return calls


def test_same_database_and_schema_initializes_once_but_explicit_initialize_runs(tmp_path,monkeypatch):
    calls=_count_migrations(monkeypatch);path=tmp_path/'knowledge.sqlite3'
    first=KnowledgeDatabase(path);KnowledgeDatabase(path);KnowledgeDatabase(path)
    assert len(calls)==1
    first.initialize();assert len(calls)==2
    with first.connect() as conn:
        assert conn.execute('PRAGMA journal_mode').fetchone()[0]=='wal'
        assert conn.execute('PRAGMA foreign_keys').fetchone()[0]==1
        assert conn.execute('PRAGMA busy_timeout').fetchone()[0]==5000
        assert conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='evidence_records'").fetchone()
    conn.close()


@pytest.mark.parametrize('change',['schema','replace','delete_recreate'])
def test_schema_or_actual_database_identity_change_reinitializes(tmp_path,monkeypatch,change):
    calls=_count_migrations(monkeypatch);path=tmp_path/'knowledge.sqlite3';db=KnowledgeDatabase(path)
    if change=='schema':
        with db.connect() as conn:conn.execute('DROP INDEX idx_evidence_session')
        conn.close()
    else:
        import gc
        gc.collect()
        if change=='replace':
            other=tmp_path/'other.sqlite3';KnowledgeDatabase(other)
            gc.collect();other.replace(path)
        else:path.unlink()
    before=len(calls);db=KnowledgeDatabase(path);assert len(calls)==before+1
    with db.connect() as conn:assert conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_evidence_session'").fetchone()
    conn.close()


def test_concurrent_constructors_share_only_verified_initialization(tmp_path,monkeypatch):
    calls=_count_migrations(monkeypatch);path=tmp_path/'knowledge.sqlite3'
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(lambda _:KnowledgeDatabase(path),range(8)))
    assert len(calls)==1


def test_failed_initialization_is_retried_not_cached(tmp_path,monkeypatch):
    calls=[];original=KnowledgeDatabase._migrate
    def migrate(self,conn):
        calls.append(1)
        if len(calls)==1:raise sqlite3.OperationalError('controlled migration failure')
        return original(self,conn)
    monkeypatch.setattr(KnowledgeDatabase,'_migrate',migrate);path=tmp_path/'knowledge.sqlite3'
    with pytest.raises(sqlite3.OperationalError):KnowledgeDatabase(path)
    KnowledgeDatabase(path);KnowledgeDatabase(path);assert len(calls)==2


def test_warm_cache_still_opens_real_database_and_surfaces_access_failure(tmp_path,monkeypatch):
    path=tmp_path/'knowledge.sqlite3';KnowledgeDatabase(path)
    def denied(self):raise PermissionError('controlled actual connection denial')
    monkeypatch.setattr(KnowledgeDatabase,'connect',denied)
    with pytest.raises(PermissionError):KnowledgeDatabase(path)


@pytest.mark.parametrize('proof',['identity','schema'])
def test_unverifiable_identity_or_schema_never_skips_initialization(tmp_path,monkeypatch,proof):
    calls=_count_migrations(monkeypatch)
    if proof=='identity':monkeypatch.setattr(KnowledgeDatabase,'_database_identity',lambda self:None)
    else:monkeypatch.setattr(KnowledgeDatabase,'_schema_version',staticmethod(lambda conn:None))
    path=tmp_path/'knowledge.sqlite3';KnowledgeDatabase(path);KnowledgeDatabase(path);assert len(calls)==2


def test_data_write_does_not_change_schema_or_suppress_real_transaction(tmp_path,monkeypatch):
    calls=_count_migrations(monkeypatch);path=tmp_path/'knowledge.sqlite3';db=KnowledgeDatabase(path)
    with db.connect() as conn:conn.execute("CREATE TABLE actual_values(value INTEGER)")
    conn.close();db=KnowledgeDatabase(path);before=len(calls)
    with db.connect() as conn:conn.execute('INSERT INTO actual_values VALUES (17)')
    conn.close();db=KnowledgeDatabase(path);assert len(calls)==before
    with db.connect() as conn:assert conn.execute('SELECT value FROM actual_values').fetchone()[0]==17
    conn.close()
