from __future__ import annotations
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from uuid import uuid4
from datetime import datetime, timezone, timedelta
import os
from main import db, current_user
from reports import ensure_reports_table

router = APIRouter(prefix='/api/trust-safety', tags=['trust-safety'])
VALID_REPORT_STATUS={'open','resolved','dismissed'}
VALID_STRIKE_STATUS={'active','removed'}
VALID_SEVERITY={'warning','low','medium','high','critical'}
VALID_APPEAL_STATUS={'pending','approved','rejected'}
VALID_ACTION={'warning','restriction','suspend','monetization_hold'}

def now(): return datetime.now(timezone.utc).isoformat()

def require_admin(authorization):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,'Login required')
    allowed={x.strip() for x in os.getenv('REELO_ADMIN_USER_IDS','').split(',') if x.strip()}
    if str(uid) not in allowed: raise HTTPException(403,'Admin access required')
    return str(uid)

def tables(c):
    ensure_reports_table(c)
    c.execute("CREATE TABLE IF NOT EXISTS safety_strikes(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,report_id TEXT,target_type TEXT,target_id TEXT,severity TEXT NOT NULL,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'active',action TEXT DEFAULT 'warning',expires_at TEXT,created_at TEXT NOT NULL,removed_at TEXT,removed_by TEXT)")
    cols={r[1] for r in c.execute('PRAGMA table_info(safety_strikes)').fetchall()}
    if 'action' not in cols: c.execute("ALTER TABLE safety_strikes ADD COLUMN action TEXT DEFAULT 'warning'")
    if 'expires_at' not in cols: c.execute("ALTER TABLE safety_strikes ADD COLUMN expires_at TEXT")
    c.execute("CREATE TABLE IF NOT EXISTS safety_appeals(id TEXT PRIMARY KEY,user_id TEXT NOT NULL,strike_id TEXT,report_id TEXT,reason TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'pending',admin_reason TEXT DEFAULT '',created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS safety_audit_log(id TEXT PRIMARY KEY,admin_id TEXT NOT NULL,action TEXT NOT NULL,target_type TEXT NOT NULL,target_id TEXT NOT NULL,details TEXT DEFAULT '',created_at TEXT NOT NULL)")
    c.execute("CREATE TABLE IF NOT EXISTS safety_restrictions(user_id TEXT PRIMARY KEY,action TEXT NOT NULL,expires_at TEXT,active INTEGER NOT NULL DEFAULT 1,reason TEXT DEFAULT '',updated_at TEXT NOT NULL)")

def audit(c,admin_id,action,target_type,target_id,details=''):
    c.execute('INSERT INTO safety_audit_log(id,admin_id,action,target_type,target_id,details,created_at) VALUES(?,?,?,?,?,?,?)',(uuid4().hex,admin_id,action,target_type,target_id,details[:1000],now()))

def refresh_expiry(c,user_id=None):
    t=now()
    if user_id:
        c.execute("UPDATE safety_strikes SET status='removed',removed_at=? WHERE user_id=? AND status='active' AND expires_at IS NOT NULL AND expires_at<=?",(t,user_id,t))
        c.execute("UPDATE safety_restrictions SET active=0,updated_at=? WHERE user_id=? AND active=1 AND expires_at IS NOT NULL AND expires_at<=?",(t,user_id,t))
    else:
        c.execute("UPDATE safety_strikes SET status='removed',removed_at=? WHERE status='active' AND expires_at IS NOT NULL AND expires_at<=?",(t,t))
        c.execute("UPDATE safety_restrictions SET active=0,updated_at=? WHERE active=1 AND expires_at IS NOT NULL AND expires_at<=?",(t,t))

def escalation(severity,count):
    if severity=='critical': return 'suspend',1
    if count>=3: return 'restriction',30
    if severity=='high': return 'restriction',14
    if severity=='medium': return 'warning',30
    return 'warning',30

class StrikeRequest(BaseModel):
    user_id:str; severity:str='warning'; reason:str; report_id:str=''; target_type:str=''; target_id:str=''; duration_days:int|None=None
class StrikeStatusRequest(BaseModel): status:str
class AppealRequest(BaseModel): strike_id:str=''; report_id:str=''; reason:str
class AppealStatusRequest(BaseModel): status:str; reason:str=''
class OverrideRequest(BaseModel): action:str; duration_days:int=7; reason:str=''

@router.get('/me')
def my_safety(authorization: str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,'Login required')
    with db() as c:
        tables(c); refresh_expiry(c,str(uid))
        strikes=c.execute("SELECT id,severity,reason,status,action,expires_at,created_at FROM safety_strikes WHERE user_id=? ORDER BY created_at DESC LIMIT 50",(str(uid),)).fetchall()
        restriction=c.execute("SELECT action,expires_at,reason,active FROM safety_restrictions WHERE user_id=?",(str(uid),)).fetchone()
        appeals=c.execute("SELECT id,strike_id,report_id,reason,status,admin_reason,created_at,updated_at FROM safety_appeals WHERE user_id=? ORDER BY created_at DESC LIMIT 50",(str(uid),)).fetchall()
        active=sum(1 for x in strikes if x['status']=='active')
    return {'active_strikes':active,'restriction':dict(restriction) if restriction else None,'strikes':[dict(x) for x in strikes],'appeals':[dict(x) for x in appeals]}

@router.post('/appeals')
def create_appeal(req:AppealRequest,authorization: str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid: raise HTTPException(401,'Login required')
    reason=req.reason.strip()
    if len(reason)<5 or len(reason)>1000: raise HTTPException(400,'Invalid appeal reason')
    with db() as c:
        tables(c); refresh_expiry(c,str(uid))
        if req.strike_id and not c.execute('SELECT id FROM safety_strikes WHERE id=? AND user_id=?',(req.strike_id,str(uid))).fetchone(): raise HTTPException(404,'Strike not found')
        if req.report_id and not c.execute('SELECT id FROM reports WHERE id=?',(req.report_id,)).fetchone(): raise HTTPException(404,'Report not found')
        duplicate=c.execute("SELECT id FROM safety_appeals WHERE user_id=? AND strike_id=? AND status='pending' LIMIT 1",(str(uid),req.strike_id.strip())).fetchone()
        if duplicate:return {'ok':True,'duplicate':True,'appeal_id':duplicate['id']}
        aid=uuid4().hex;t=now();c.execute('INSERT INTO safety_appeals(id,user_id,strike_id,report_id,reason,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)',(aid,str(uid),req.strike_id.strip(),req.report_id.strip(),reason,'pending',t,t))
    return {'ok':True,'appeal_id':aid,'status':'pending'}

@router.get('/admin/overview')
def overview(authorization: str|None=Header(default=None)):
    require_admin(authorization)
    with db() as c:
        tables(c);refresh_expiry(c)
        reports={str(r[0]):int(r[1]) for r in c.execute('SELECT status,COUNT(*) FROM reports GROUP BY status').fetchall()}
        strikes={str(r[0]):int(r[1]) for r in c.execute("SELECT severity,COUNT(*) FROM safety_strikes WHERE status='active' GROUP BY severity").fetchall()}
        appeals={str(r[0]):int(r[1]) for r in c.execute('SELECT status,COUNT(*) FROM safety_appeals GROUP BY status').fetchall()}
        restrictions=int(c.execute('SELECT COUNT(*) FROM safety_restrictions WHERE active=1').fetchone()[0])
    return {'reports':{'open':reports.get('open',0),'resolved':reports.get('resolved',0),'dismissed':reports.get('dismissed',0),'total':sum(reports.values())},'strikes':strikes,'appeals':appeals,'active_restrictions':restrictions}

@router.get('/admin/reports')
def reports(status:str='open',limit:int=100,authorization: str|None=Header(default=None)):
    require_admin(authorization);status=status.strip().lower();limit=max(1,min(limit,200))
    if status not in VALID_REPORT_STATUS|{'all'}:raise HTTPException(400,'Invalid report status')
    with db() as c:
        tables(c);where='' if status=='all' else ' WHERE r.status=?';args=() if status=='all' else (status,)
        rows=c.execute(f'''SELECT r.id,r.reporter_id,r.target_type,r.target_id,r.reason,r.details,r.status,r.created_at,COUNT(s.id) strike_count FROM reports r LEFT JOIN safety_strikes s ON s.report_id=r.id{where} GROUP BY r.id ORDER BY r.created_at DESC LIMIT ?''',args+(limit,)).fetchall()
    return {'items':[dict(r) for r in rows]}

@router.post('/admin/reports/{report_id}/status')
def report_status(report_id:str,req:StrikeStatusRequest,authorization: str|None=Header(default=None)):
    admin=require_admin(authorization);status=req.status.strip().lower()
    if status not in VALID_REPORT_STATUS:raise HTTPException(400,'Invalid report status')
    with db() as c:
        tables(c);row=c.execute('SELECT id FROM reports WHERE id=?',(report_id,)).fetchone()
        if not row:raise HTTPException(404,'Report not found')
        c.execute('UPDATE reports SET status=? WHERE id=?',(status,report_id));audit(c,admin,'report_status','report',report_id,status)
    return {'ok':True,'status':status}

@router.get('/admin/strikes')
def strikes(status:str='active',limit:int=100,authorization: str|None=Header(default=None)):
    require_admin(authorization);status=status.strip().lower();limit=max(1,min(limit,200))
    if status not in VALID_STRIKE_STATUS|{'all'}:raise HTTPException(400,'Invalid strike status')
    with db() as c:
        tables(c);refresh_expiry(c);where='' if status=='all' else ' WHERE status=?';args=() if status=='all' else (status,);rows=c.execute(f'SELECT * FROM safety_strikes{where} ORDER BY created_at DESC LIMIT ?',args+(limit,)).fetchall()
    return {'items':[dict(x) for x in rows]}

@router.post('/admin/strikes')
def create_strike(req:StrikeRequest,authorization: str|None=Header(default=None)):
    admin=require_admin(authorization);severity=req.severity.strip().lower();reason=req.reason.strip();uid=req.user_id.strip()
    if not uid or severity not in VALID_SEVERITY:raise HTTPException(400,'Invalid strike data')
    if len(reason)<3 or len(reason)>500:raise HTTPException(400,'Invalid strike reason')
    with db() as c:
        tables(c);refresh_expiry(c,uid);count=int(c.execute("SELECT COUNT(*) FROM safety_strikes WHERE user_id=? AND status='active'",(uid,)).fetchone()[0]);action,default_days=escalation(severity,count+1);days=req.duration_days if req.duration_days is not None else default_days;days=max(1,min(days,3650));expires=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat();sid=uuid4().hex
        c.execute('INSERT INTO safety_strikes(id,user_id,report_id,target_type,target_id,severity,reason,status,action,expires_at,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(sid,uid,req.report_id.strip(),req.target_type.strip(),req.target_id.strip(),severity,reason,'active',action,expires,now()))
        if req.report_id.strip():c.execute("UPDATE reports SET status='resolved' WHERE id=?",(req.report_id.strip(),))
        if action in {'restriction','suspend','monetization_hold'}:
            c.execute("INSERT INTO safety_restrictions(user_id,action,expires_at,active,reason,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET action=excluded.action,expires_at=excluded.expires_at,active=1,reason=excluded.reason,updated_at=excluded.updated_at",(uid,action,expires,1,reason,now()))
        audit(c,admin,'strike_created','user',uid,f'{severity}/{action}: {reason}')
    return {'ok':True,'strike_id':sid,'action':action,'expires_at':expires,'active_strikes':count+1}

@router.post('/admin/strikes/{strike_id}/status')
def strike_status(strike_id:str,req:StrikeStatusRequest,authorization: str|None=Header(default=None)):
    admin=require_admin(authorization);status=req.status.strip().lower()
    if status not in VALID_STRIKE_STATUS:raise HTTPException(400,'Invalid strike status')
    with db() as c:
        tables(c);row=c.execute('SELECT id,status,user_id FROM safety_strikes WHERE id=?',(strike_id,)).fetchone()
        if not row:raise HTTPException(404,'Strike not found')
        if row['status']==status:return {'ok':True,'status':status}
        if status=='removed':c.execute("UPDATE safety_strikes SET status='removed',removed_at=?,removed_by=? WHERE id=?",(now(),admin,strike_id))
        else:c.execute("UPDATE safety_strikes SET status='active',removed_at=NULL,removed_by=NULL WHERE id=?",(strike_id,))
        audit(c,admin,'strike_status','strike',strike_id,status)
    return {'ok':True,'status':status}

@router.get('/admin/appeals')
def appeals(status:str='pending',limit:int=100,authorization: str|None=Header(default=None)):
    require_admin(authorization);status=status.strip().lower();limit=max(1,min(limit,200))
    if status not in VALID_APPEAL_STATUS|{'all'}:raise HTTPException(400,'Invalid appeal status')
    with db() as c:
        tables(c);where='' if status=='all' else ' WHERE a.status=?';args=() if status=='all' else (status,);rows=c.execute(f'''SELECT a.*,s.severity,s.reason strike_reason,s.action strike_action,s.expires_at strike_expires_at FROM safety_appeals a LEFT JOIN safety_strikes s ON s.id=a.strike_id{where} ORDER BY a.created_at DESC LIMIT ?''',args+(limit,)).fetchall()
    return {'items':[dict(x) for x in rows]}

@router.post('/admin/appeals/{appeal_id}/status')
def appeal_status(appeal_id:str,req:AppealStatusRequest,authorization: str|None=Header(default=None)):
    admin=require_admin(authorization);status=req.status.strip().lower();reason=req.reason.strip()
    if status not in VALID_APPEAL_STATUS:raise HTTPException(400,'Invalid appeal status')
    if status!='pending' and len(reason)<3:raise HTTPException(400,'Decision reason is required')
    with db() as c:
        tables(c);row=c.execute('SELECT * FROM safety_appeals WHERE id=?',(appeal_id,)).fetchone()
        if not row:raise HTTPException(404,'Appeal not found')
        if row['status']!='pending':raise HTTPException(409,'Appeal already decided')
        c.execute('UPDATE safety_appeals SET status=?,admin_reason=?,updated_at=? WHERE id=?',(status,reason,now(),appeal_id))
        if row['strike_id'] and status=='approved':c.execute("UPDATE safety_strikes SET status='removed',removed_at=?,removed_by=? WHERE id=?",(now(),admin,row['strike_id']))
        audit(c,admin,'appeal_decided','appeal',appeal_id,f'{status}: {reason}')
    return {'ok':True,'status':status}

@router.post('/admin/users/{user_id}/override')
def override_user(user_id:str,req:OverrideRequest,authorization: str|None=Header(default=None)):
    admin=require_admin(authorization);action=req.action.strip().lower()
    if action not in VALID_ACTION|{'clear'}:raise HTTPException(400,'Invalid enforcement action')
    with db() as c:
        tables(c)
        if action=='clear':c.execute("UPDATE safety_restrictions SET active=0,updated_at=? WHERE user_id=?",(now(),user_id))
        else:
            days=max(1,min(req.duration_days,3650));expires=(datetime.now(timezone.utc)+timedelta(days=days)).isoformat();c.execute("INSERT INTO safety_restrictions(user_id,action,expires_at,active,reason,updated_at) VALUES(?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET action=excluded.action,expires_at=excluded.expires_at,active=1,reason=excluded.reason,updated_at=excluded.updated_at",(user_id,action,expires,1,req.reason[:500],now()))
        audit(c,admin,'admin_override','user',user_id,f'{action}: {req.reason}')
    return {'ok':True,'action':action}

@router.get('/admin/audit')
def audit_log(limit:int=200,authorization: str|None=Header(default=None)):
    require_admin(authorization);limit=max(1,min(limit,500))
    with db() as c:
        tables(c);rows=c.execute('SELECT * FROM safety_audit_log ORDER BY created_at DESC LIMIT ?',(limit,)).fetchall()
    return {'items':[dict(x) for x in rows]}
