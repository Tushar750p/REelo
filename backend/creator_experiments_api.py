from fastapi import APIRouter, Header, HTTPException
from main import db, current_user
from uuid import uuid4
from datetime import datetime

router = APIRouter(prefix="/api/creator/experiments", tags=["creator-experiments"])


def uid_or_401(authorization):
    uid = current_user(authorization)
    if not uid:
        raise HTTPException(401, "Login required")
    return uid


def ensure_tables(c):
    c.execute("""CREATE TABLE IF NOT EXISTS creator_experiments(
        id TEXT PRIMARY KEY, creator_id TEXT NOT NULL, name TEXT NOT NULL,
        hypothesis TEXT NOT NULL DEFAULT '', metric TEXT NOT NULL DEFAULT 'views',
        status TEXT NOT NULL DEFAULT 'active', variant_a TEXT NOT NULL DEFAULT '',
        variant_b TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        completed_at TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS creator_experiment_results(
        id TEXT PRIMARY KEY, experiment_id TEXT NOT NULL, variant TEXT NOT NULL,
        views INTEGER NOT NULL DEFAULT 0, interactions INTEGER NOT NULL DEFAULT 0,
        watch_seconds REAL NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def result_summary(c, experiment_id):
    rows = c.execute("SELECT variant,SUM(views) views,SUM(interactions) interactions,SUM(watch_seconds) watch_seconds,COUNT(*) samples FROM creator_experiment_results WHERE experiment_id=? GROUP BY variant", (experiment_id,)).fetchall()
    out = {}
    for r in rows:
        d = dict(r); views = int(d['views'] or 0); interactions = int(d['interactions'] or 0)
        d['interaction_rate'] = round(interactions / views * 100, 2) if views else 0
        d['avg_watch_seconds'] = round(float(d['watch_seconds'] or 0) / max(int(d['samples'] or 0), 1), 2)
        out[d['variant']] = d
    return out


@router.get("")
def list_experiments(authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    with db() as c:
        ensure_tables(c)
        rows = c.execute("SELECT * FROM creator_experiments WHERE creator_id=? ORDER BY created_at DESC", (uid,)).fetchall()
        items=[]
        for r in rows:
            item=dict(r); item['results']=result_summary(c,item['id']); items.append(item)
    return {'items':items}


@router.post("")
def create_experiment(name: str, hypothesis: str = '', metric: str = 'views', variant_a: str = '', variant_b: str = '', authorization: str | None = Header(default=None)):
    uid = uid_or_401(authorization)
    allowed={'views','interactions','watch_seconds','interaction_rate'}
    if metric not in allowed: raise HTTPException(400, 'Unsupported experiment metric')
    if not name.strip() or not variant_a.strip() or not variant_b.strip(): raise HTTPException(400, 'Name and both variants are required')
    eid=uuid4().hex
    with db() as c:
        ensure_tables(c)
        c.execute("INSERT INTO creator_experiments(id,creator_id,name,hypothesis,metric,variant_a,variant_b) VALUES(?,?,?,?,?,?,?)", (eid,uid,name.strip(),hypothesis.strip(),metric,variant_a.strip(),variant_b.strip()))
    return {'created':True,'id':eid}


@router.post('/{experiment_id}/results')
def add_result(experiment_id: str, variant: str, views: int = 0, interactions: int = 0, watch_seconds: float = 0, notes: str = '', authorization: str | None = Header(default=None)):
    uid=uid_or_401(authorization)
    if variant not in {'A','B'}: raise HTTPException(400,'Variant must be A or B')
    with db() as c:
        ensure_tables(c)
        owner=c.execute('SELECT id FROM creator_experiments WHERE id=? AND creator_id=?',(experiment_id,uid)).fetchone()
        if not owner: raise HTTPException(404,'Experiment not found')
        rid=uuid4().hex
        c.execute('INSERT INTO creator_experiment_results(id,experiment_id,variant,views,interactions,watch_seconds,notes) VALUES(?,?,?,?,?,?,?)',(rid,experiment_id,variant,max(0,int(views)),max(0,int(interactions)),max(0,float(watch_seconds)),notes.strip()))
        summary=result_summary(c,experiment_id)
    return {'saved':True,'result_id':rid,'results':summary}


@router.post('/{experiment_id}/complete')
def complete_experiment(experiment_id: str, authorization: str | None = Header(default=None)):
    uid=uid_or_401(authorization)
    with db() as c:
        ensure_tables(c)
        row=c.execute('SELECT id FROM creator_experiments WHERE id=? AND creator_id=?',(experiment_id,uid)).fetchone()
        if not row: raise HTTPException(404,'Experiment not found')
        c.execute("UPDATE creator_experiments SET status='completed',completed_at=? WHERE id=?",(datetime.utcnow().isoformat(),experiment_id))
        summary=result_summary(c,experiment_id)
    return {'completed':True,'results':summary,'note':'The comparison describes observed experiment data; it does not establish causality or guarantee future performance.'}
