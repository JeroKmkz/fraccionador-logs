from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import re
import uuid
from typing import List, Dict, Optional
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="8.1.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento de sesiones en memoria
sessions_storage = {}

class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_access = datetime.now()
        self.raw_chunks = []
        self.total_lines = 0
        self.processed = False
        self.questions = []
        self.metadata = {}

class UploadTextRequest(BaseModel):
    content: str  # El contenido del log como texto
    filename: Optional[str] = "log.txt"

class ProcessSessionRequest(BaseModel):
    session_id: str

def clean_irc_codes(text: str) -> str:
    """Limpia códigos IRC del texto"""
    text = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', text)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'(?:^|\s)\d+,\d+\s+', ' ', text)
    return text.strip()

def split_into_chunks(text: str, chunk_size: int = 500) -> List[str]:
    """Divide el texto en chunks de N líneas"""
    lines = text.split('\n')
    chunks = []
    
    for i in range(0, len(lines), chunk_size):
        chunk = '\n'.join(lines[i:i + chunk_size])
        chunks.append(chunk)
    
    return chunks

def extract_questions_from_text(text: str) -> List[Dict]:
    """Extrae todas las preguntas del texto"""
    lines = text.split('\n')
    questions = []
    current_q = None
    
    for i, line in enumerate(lines):
        clean_line = clean_irc_codes(line)
        
        # Detectar nueva pregunta
        pregunta_match = re.search(r'Pregunta:\s*(\d+)\s*/\s*(\d+)', clean_line)
        if pregunta_match:
            if current_q and current_q.get('pregunta'):
                questions.append(current_q)
            
            current_q = {
                'numero': int(pregunta_match.group(1)),
                'total': int(pregunta_match.group(2)),
                'categoria': '',
                'pregunta': '',
                'ganador': '',
                'respuesta': '',
                'tiempo_respuesta': '',
                'participantes': []
            }
            continue
            
        if current_q:
            # Detectar categoría y pregunta
            categorias = ['MEDICINA-SALUD', 'GASTRONOMÍA', 'INFORMÁTICA', 'DEPORTE', 
                         'HISTORIA', 'GEOGRAFÍA', 'CIENCIAS', 'ARTE', 'CINE', 'MÚSICA',
                         'LITERATURA', 'TELEVISIÓN', 'POLÍTICA', 'ECONOMÍA', 'MISCELÁNEA']
            
            for cat in categorias:
                if cat in clean_line.upper() and not current_q['categoria']:
                    current_q['categoria'] = cat
                    parts = re.split(cat, clean_line.upper())
                    if len(parts) > 1:
                        pregunta_text = clean_line[clean_line.upper().find(cat) + len(cat):]
                        pregunta_text = re.sub(r'\([^)]*palabras?\)', '', pregunta_text)
                        current_q['pregunta'] = pregunta_text.strip()
                    break
            
            # Detectar ganador
            if '>>>' in clean_line and not current_q['ganador']:
                if 'scratchea' not in clean_line.lower() and ' a ' in clean_line:
                    ganador_match = re.search(r'>>>(\w+)', clean_line)
                    if ganador_match:
                        current_q['ganador'] = ganador_match.group(1)
                        tiempo_match = re.search(r'(\d+)[\'"](\d+)', clean_line)
                        if tiempo_match:
                            current_q['tiempo_respuesta'] = f"{tiempo_match.group(1)}.{tiempo_match.group(2)}s"
            
            # Detectar participantes
            if '>>>' in clean_line:
                player_match = re.search(r'>>>(\w+)', clean_line)
                if player_match:
                    player = player_match.group(1)
                    if player not in current_q['participantes']:
                        current_q['participantes'].append(player)
            
            # Detectar respuesta correcta
            if 'La buena:' in clean_line or 'Las buenas:' in clean_line:
                respuesta_match = re.search(r'(?:La buena:|Las buenas:)\s*([^]+?)(?:Mandada por:|$)', clean_line)
                if respuesta_match:
                    current_q['respuesta'] = respuesta_match.group(1).strip()
    
    if current_q and current_q.get('pregunta'):
        questions.append(current_q)
    
    return questions

@app.post("/upload_text_log")
async def upload_text_log(request: UploadTextRequest):
    """
    Endpoint para ChatGPT: Recibe el log como texto plano
    """
    try:
        text = request.content
        
        if not text:
            raise HTTPException(status_code=400, detail="Contenido vacío")
        
        # Limpiar el texto de códigos IRC
        text = clean_irc_codes(text)
        
        # Generar session_id único
        session_id = str(uuid.uuid4())[:8]
        
        # Crear sesión
        session = SessionData(session_id)
        
        # Dividir en chunks de 500 líneas
        chunks = split_into_chunks(text, chunk_size=500)
        session.raw_chunks = chunks
        session.total_lines = len(text.split('\n'))
        
        # Detección rápida de preguntas
        estimated_questions = len(re.findall(r'Pregunta:\s*\d+\s*/\s*\d+', text))
        
        # Guardar metadatos
        session.metadata = {
            'filename': request.filename,
            'size_bytes': len(text),
            'total_chunks': len(chunks),
            'estimated_questions': estimated_questions
        }
        
        # Almacenar sesión
        sessions_storage[session_id] = session
        
        # Limpiar sesiones antiguas
        cleanup_old_sessions()
        
        return JSONResponse({
            "session_id": session_id,
            "total_lines": session.total_lines,
            "total_chunks": len(chunks),
            "estimated_questions": estimated_questions,
            "message": f"Log recibido y troceado en {len(chunks)} chunks.",
            "next_step": f"Usa POST /process_session con session_id: {session_id}"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)[:200]}")

@app.post("/upload_full_log")
async def upload_full_log(file: UploadFile = File(...)):
    """
    Endpoint para pruebas locales con archivo real (NO funciona desde ChatGPT)
    """
    try:
        content = await file.read()
        
        text = None
        for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
            try:
                text = content.decode(encoding)
                break
            except:
                continue
        
        if not text:
            raise HTTPException(status_code=400, detail="No se pudo decodificar")
        
        # Usar la misma lógica que upload_text_log
        text = clean_irc_codes(text)
        session_id = str(uuid.uuid4())[:8]
        session = SessionData(session_id)
        
        chunks = split_into_chunks(text, chunk_size=500)
        session.raw_chunks = chunks
        session.total_lines = len(text.split('\n'))
        estimated_questions = len(re.findall(r'Pregunta:\s*\d+\s*/\s*\d+', text))
        
        session.metadata = {
            'filename': file.filename,
            'size_bytes': len(content),
            'total_chunks': len(chunks),
            'estimated_questions': estimated_questions
        }
        
        sessions_storage[session_id] = session
        cleanup_old_sessions()
        
        return JSONResponse({
            "session_id": session_id,
            "total_lines": session.total_lines,
            "total_chunks": len(chunks),
            "estimated_questions": estimated_questions,
            "message": f"Archivo procesado: {len(chunks)} chunks.",
            "next_step": f"Usa POST /process_session con session_id: {session_id}"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.post("/process_session")
async def process_session(request: ProcessSessionRequest):
    """Procesa todos los chunks de una sesión"""
    if request.session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    try:
        session = sessions_storage[request.session_id]
        session.last_access = datetime.now()
        
        full_text = '\n'.join(session.raw_chunks)
        session.questions = extract_questions_from_text(full_text)
        session.processed = True
        
        categories_count = {}
        for q in session.questions:
            if q['categoria']:
                categories_count[q['categoria']] = categories_count.get(q['categoria'], 0) + 1
        
        equipos = detectar_equipos(full_text)
        
        return JSONResponse({
            "session_id": request.session_id,
            "total_questions": len(session.questions),
            "categories": categories_count,
            "equipos": equipos,
            "message": f"Procesadas {len(session.questions)} preguntas.",
            "next_step": f"GET /get_questions/{request.session_id}/1/5"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

@app.get("/get_questions/{session_id}/{start}/{end}")
async def get_questions(session_id: str, start: int, end: int):
    """Devuelve un rango de preguntas procesadas"""
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions_storage[session_id]
    session.last_access = datetime.now()
    
    if not session.processed:
        raise HTTPException(status_code=400, detail="Sesión no procesada")
    
    start_idx = max(0, start - 1)
    end_idx = min(end, len(session.questions))
    
    questions_slice = session.questions[start_idx:end_idx]
    
    return JSONResponse({
        "session_id": session_id,
        "questions": questions_slice,
        "returned_range": f"{start}-{end_idx}",
        "total_questions": len(session.questions),
        "has_more": end_idx < len(session.questions),
        "next_range": f"{end_idx + 1}-{min(end_idx + 5, len(session.questions))}" if end_idx < len(session.questions) else None
    })

@app.get("/get_summary/{session_id}")
async def get_summary(session_id: str):
    """Resumen de la partida"""
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions_storage[session_id]
    
    if not session.processed:
        raise HTTPException(status_code=400, detail="Sesión no procesada")
    
    ganadores_count = {}
    for q in session.questions:
        if q['ganador']:
            ganadores_count[q['ganador']] = ganadores_count.get(q['ganador'], 0) + 1
    
    top_players = sorted(ganadores_count.items(), key=lambda x: x[1], reverse=True)[:3]
    
    return JSONResponse({
        "session_id": session_id,
        "total_questions": len(session.questions),
        "top_players": [{"player": p[0], "correct_answers": p[1]} for p in top_players],
        "metadata": session.metadata
    })

def detectar_equipos(text: str) -> List[str]:
    """Detecta equipos participantes"""
    equipos = []
    
    if 'FOGUETES' in text[:2000]:
        equipos.append('FOGUETES')
    if 'LIDERES' in text[:2000] or 'LÍDERES' in text[:2000]:
        equipos.append('LIDERES')
    
    return equipos

def cleanup_old_sessions():
    """Limpia sesiones de más de 2 horas"""
    cutoff = datetime.now() - timedelta(hours=2)
    expired = [sid for sid, session in sessions_storage.items() 
              if session.created_at < cutoff]
    for sid in expired:
        del sessions_storage[sid]

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "8.1.0",
        "status": "active",
        "active_sessions": len(sessions_storage),
        "endpoints": {
            "for_chatgpt": [
                "POST /upload_text_log - Sube log como texto",
                "POST /process_session - Procesa sesión",
                "GET /get_questions/{id}/{start}/{end} - Obtiene preguntas",
                "GET /get_summary/{id} - Resumen"
            ],
            "for_testing": [
                "POST /upload_full_log - Sube archivo (solo pruebas)"
            ]
        }
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "sessions": len(sessions_storage),
        "memory_mb": sum(
            sum(len(chunk) for chunk in s.raw_chunks) 
            for s in sessions_storage.values()
        ) / (1024 * 1024)
    }
