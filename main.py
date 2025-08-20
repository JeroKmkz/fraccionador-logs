from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import uuid
from typing import List, Dict, Optional
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="6.0.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento en memoria
sessions = {}

class FileSession:
    def __init__(self, questions: List[Dict]):
        self.questions = questions
        self.created_at = datetime.now()
        
class MinimalResponse(BaseModel):
    sid: str  # session_id abreviado
    tot: int  # total
    b: int    # batch number
    tb: int   # total batches
    nxt: bool # has next
    q: List[Dict]  # questions

def limpiar_log_irc(text: bytes) -> str:
    """Limpia códigos IRC del texto binario"""
    try:
        text_str = text.decode('utf-8', errors='ignore')
    except:
        text_str = text.decode('latin-1', errors='ignore')
    
    # Eliminar códigos de color IRC
    text_str = re.sub(b'\x03\d{0,2}(?:,\d{1,2})?'.decode('utf-8', errors='ignore'), '', text_str)
    text_str = re.sub(b'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]'.decode('utf-8', errors='ignore'), '', text_str)
    text_str = re.sub(r'(?:^|\s)\d+,\d+\s+', ' ', text_str)
    
    return text_str

def extract_questions_minimal(text: str) -> List[Dict]:
    """Extrae solo la información ESENCIAL de las preguntas"""
    lines = text.split('\n')
    questions = []
    current_q = None
    
    for line in lines:
        # Detectar nueva pregunta
        pregunta_match = re.search(r'Pregunta:\s*(\d+)\s*/\s*(\d+)', line)
        if pregunta_match:
            if current_q and current_q.get('p'):  # Solo guardar si tiene contenido
                questions.append(current_q)
            
            current_q = {
                'n': int(pregunta_match.group(1)),  # numero
                'c': '',  # categoria (abreviada)
                'p': '',  # pregunta (primeras 50 chars)
                'g': '',  # ganador
                'r': ''   # respuesta correcta (primeras 30 chars)
            }
            continue
            
        if current_q:
            # Detectar categoría
            categorias = {
                'MEDICINA-SALUD': 'MED',
                'GASTRONOMÍA': 'GAS', 
                'INFORMÁTICA': 'INF',
                'DEPORTE': 'DEP',
                'HISTORIA': 'HIS',
                'GEOGRAFÍA': 'GEO',
                'CIENCIAS': 'CIE',
                'ARTE': 'ART',
                'CINE': 'CIN',
                'MÚSICA': 'MUS',
                'LITERATURA': 'LIT',
                'TELEVISIÓN': 'TV',
                'POLÍTICA': 'POL',
                'ECONOMÍA': 'ECO'
            }
            
            for cat_full, cat_abbr in categorias.items():
                if cat_full in line and not current_q['c']:
                    current_q['c'] = cat_abbr
                    # Extraer pregunta (máximo 60 caracteres)
                    pregunta_text = re.split(cat_full, line)[-1]
                    pregunta_text = re.sub(r'\([^)]*palabras?\)', '', pregunta_text).strip()
                    current_q['p'] = pregunta_text[:60]
                    break
            
            # Detectar primer ganador
            if '>>>' in line and not current_q['g'] and 'scratchea' not in line:
                player_match = re.search(r'>>>(\w+)', line)
                if player_match:
                    current_q['g'] = player_match.group(1)
            
            # Detectar respuesta correcta (máximo 40 caracteres)
            if ('La buena:' in line or 'Las buenas:' in line) and not current_q['r']:
                respuesta_match = re.search(r'(?:La buena:|Las buenas:)\s*([^]+?)(?:Mandada por:|$)', line)
                if respuesta_match:
                    current_q['r'] = respuesta_match.group(1).strip()[:40]
    
    # Agregar última pregunta
    if current_q and current_q.get('p'):
        questions.append(current_q)
    
    return questions

@app.post("/process")
async def process_file(file: UploadFile = File(...)):
    """Procesa archivo y devuelve respuesta MINIMALISTA"""
    try:
        # Leer y limpiar archivo
        content = await file.read()
        cleaned_text = limpiar_log_irc(content)
        
        # Extraer preguntas con formato minimal
        all_questions = extract_questions_minimal(cleaned_text)
        
        if not all_questions:
            raise HTTPException(status_code=400, detail="No questions found")
        
        # Generar ID de sesión corto
        session_id = str(uuid.uuid4())[:8]
        
        # Guardar en memoria
        sessions[session_id] = FileSession(all_questions)
        
        # Limpiar sesiones antiguas
        cutoff = datetime.now() - timedelta(hours=1)
        expired = [sid for sid, s in sessions.items() if s.created_at < cutoff]
        for sid in expired:
            del sessions[sid]
        
        # Preparar respuesta con solo 5 preguntas para mantener < 100KB
        BATCH_SIZE = 5
        first_batch = all_questions[:BATCH_SIZE]
        total_batches = (len(all_questions) + BATCH_SIZE - 1) // BATCH_SIZE
        
        return MinimalResponse(
            sid=session_id,
            tot=len(all_questions),
            b=1,
            tb=total_batches,
            nxt=len(all_questions) > BATCH_SIZE,
            q=first_batch
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)[:100])

@app.get("/next/{sid}/{b}")
async def get_next_batch(sid: str, b: int):
    """Obtiene el siguiente batch de preguntas"""
    if sid not in sessions:
        raise HTTPException(status_code=404, detail="Session expired")
    
    session = sessions[sid]
    BATCH_SIZE = 5
    
    total_questions = len(session.questions)
    total_batches = (total_questions + BATCH_SIZE - 1) // BATCH_SIZE
    
    if b < 1 or b > total_batches:
        raise HTTPException(status_code=400, detail="Invalid batch")
    
    start = (b - 1) * BATCH_SIZE
    end = min(start + BATCH_SIZE, total_questions)
    
    return MinimalResponse(
        sid=sid,
        tot=total_questions,
        b=b,
        tb=total_batches,
        nxt=b < total_batches,
        q=session.questions[start:end]
    )

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "6.0.0",
        "status": "active",
        "sessions": len(sessions)
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "sessions": len(sessions)}
