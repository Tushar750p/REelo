def update_me(data:ProfileUpdate,authorization:str|None=Header(default=None)):
    uid=current_user(authorization)
    if not uid:raise HTTPException(401,"Login required")
    with db() as c:
        r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
        if not r:raise HTTPException(404,"User not found")
        display=(data.display_name if data.display_name is not None else r["display_name"]).strip(); bio=(data.bio if data.bio is not None else r["bio"]).strip()
        if not display or len(display)>80 or len(bio)>160:raise HTTPException(400,"Invalid profile data")
        c.execute("UPDATE users SET display_name=?,bio=? WHERE id=?",(display,bio,uid)); r=c.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    return {"user":public_user(r)}
def feed_rows(c,uid,limit,following_only=False):
    if following_only:
        if not uid:return []
        return c.execute("SELECT v.*,u.username,u.display_name,CASE WHEN EXISTS(SELECT 1 FROM likes l WHERE l.video_id=v.id AND l.user_id=?) THEN 1 ELSE 0 END liked FROM videos v JOIN users u ON u.id=v.user_id JOIN follows f ON f.following_id=v.user_id AND f.follower_id=? WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT ?",(uid,uid,limit)).fetchall()
    return c.execute("SELECT v.*,u.username,u.display_name,CASE WHEN EXISTS(SELECT 1 FROM likes l WHERE l.video_id=v.id AND l.user_id=?) THEN 1 ELSE 0 END liked FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' ORDER BY v.created_at DESC LIMIT ?",(uid,limit)).fetchall()
@app.get("/api/feed")
def feed(limit:int=20,following:bool=False,mode:str|None=None,authorization:str|None=Header(default=None)):
    if mode is not None:following=mode.strip().lower()=="following"
    uid=current_user(authorization);limit=max(1,min(limit,50))
    with db() as c:r=feed_rows(c,uid,limit,following)
    return {"items":[dict(x) for x in r],"algorithm":"following-v1" if following else "hybrid-v1","following":following}
@app.get("/api/search")
def search(q:str):
    with db() as c:r=c.execute("SELECT v.*,u.username,u.display_name FROM videos v JOIN users u ON u.id=v.user_id WHERE v.status='ready' AND (v.caption LIKE ? OR u.username LIKE ?) ORDER BY v.created_at DESC LIMIT 50",(f"%{q.strip()}%",f"%{q.strip()}%")).fetchall()
    return {"query":q,"items":[dict(x) for x in r]}
@app.post("/api/videos/upload")