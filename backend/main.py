from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from uuid import uuid4
import shutil

app = FastAPI(title='REelo API', version='0.1.0')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
MEDIA = Path(__file__).parent / 'media'
MEDIA.mkdir(exist_ok=True)

videos = [
    {'id':'demo-1','creator':'@reelo_creator','caption':'Build your vibe. Share your story. 🚀','likes':12400,'comments':321,'tags':['REelo','AI','creator']},
    {'id':'demo-2','creator':'@futuredaily','caption':'AI is changing how we create.','likes':8700,'comments':142,'tags':['technology','future']},
]

@app.get('/health')
def health(): return {'status':'ok','service':'reelo-api','ai':'ready'}

@app.get('/api/feed')
def feed(limit:int=20): return {'items': videos[:limit], 'algorithm':'hybrid-ai-v1'}

@app.get('/api/search')
def search(q:str):
    q=q.lower().strip(); return {'query':q,'items':[v for v in videos if q in v['caption'].lower() or any(q in t.lower() for t in v['tags']) or q in v['creator'].lower()]}

@app.post('/api/videos/upload')
async def upload_video(file: UploadFile=File(...), caption:str=Form(''), creator:str=Form('@new_creator')):
    ext=Path(file.filename or 'video.mp4').suffix or '.mp4'; name=f'{uuid4().hex}{ext}'; dest=MEDIA/name
    with dest.open('wb') as out: shutil.copyfileobj(file.file, out)
    item={'id':name,'creator':creator,'caption':caption,'likes':0,'comments':0,'tags':[],'status':'uploaded','ai_moderation':'pending'}
    videos.insert(0,item); return item

@app.post('/api/events/watch')
def watch(video_id:str, seconds:float=0, action:str='view'):
    # Production: send to event queue and recommendation feature store.
    return {'accepted':True,'video_id':video_id,'seconds':seconds,'action':action}
