from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import re
import uuid
import base64
from typing import List, Dict, Optional
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="9.0.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento de sesiones
sessions_storage = {}

class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_access = datetime.now()
        self.base64_chunks = []  # Chunks de base64
        self.raw_text = ""  # Texto decodificado completo
        self.text_chunks = []  # Chunks de texto procesado
        self.total_lines = 0
        self.processed = False
        self.questions = []
        self.metadata = {}

class InitBase64Request(BaseModel):
    """Inicia una sesión y envía el primer chunk de base64"""
    first_chunk: str  # Primer chunk de base64 (máx 50KB)
    total_size: Optional[int] = None  # Tamaño total esperado
    filename: Optional[str] = "log.txt"

class AppendBase64Request(BaseModel):
    """Añade más chunks de base64 a una sesión"""
    session_id: str
    chunk: str  # Siguiente chunk de base64
    is_final: bool = False  # Si es el último chunk

class ProcessSessionRequest(BaseModel):
    session_id: str

def clean_irc_codes(text: str) -> str:
    """Limpia códigos IRC del texto"""
    text = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', text)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'(?:^|\s)\d+,\d+\s+', ' ', text)
    return text.strip()

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
                'tiempo': '',
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
            
            # Detectar participantes
            if '>>>' in clean_line:
                player_match = re.search(r'>>>(\w+)', clean_line)
                if player_match and player_match.group(1) not in current_q['participantes']:
                    current_q['participantes'].append(player_match.group(1))
            
            # Detectar respuesta
            if 'La buena:' in clean_line or 'Las buenas:' in clean_line:
                respuesta_match = re.search(r'(?:La buena:|Las buenas:)\s*([^]+?)(?:Mandada por:|$)', clean_line)
                if respuesta_match:
                    current_q['respuesta'] = respuesta_match.group(1).strip()
    
    if current_q and current_q.get('pregunta'):
        questions.append(current_q)
    
    return questions

@app.post("/init_base64_session")
async def init_base64_session(request: InitBase64Request):
    """Inicia una sesión nueva y recibe el primer chunk de base64"""
    try:
        # Generar session_id
        session_id = str(uuid.uuid4())[:8]
        
        # Crear sesión
        session = SessionData(session_id)
        session.base64_chunks.append(request.first_chunk)
        session.metadata = {
            'filename': request.filename,
            'total_size': request.total_size,
            'chunks_received': 1
        }
        
        # Guardar sesión
        sessions_storage[session_id] = session
        
        # Limpiar sesiones viejas
        cleanup_old_sessions()
        
        return JSONResponse({
            "session_id": session_id,
            "chunks_received": 1,
            "message": "Sesión iniciada. Envía más chunks con /append_base64",
            "next_step": f"POST /append_base64 con session_id: {session_id}"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)[:200]}")

@app.post("/append_base64")
async def append_base64(request: AppendBase64Request):
    """Añade más chunks de base64 a una sesión existente"""
    if request.session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    try:
        session = sessions_storage[request.session_id]
        session.last_access = datetime.now()
        
        # Añadir chunk
        session.base64_chunks.append(request.chunk)
        session.metadata['chunks_received'] += 1
        
        response = {
            "session_id": request.session_id,
            "chunks_received": session.metadata['chunks_received'],
            "message": "Chunk añadido"
        }
        
        # Si es el último chunk, decodificar todo
        if request.is_final:
            try:
                # Unir todos los chunks
                full_base64 = ''.join(session.base64_chunks)
                
                # Decodificar
                content_bytes = base64.b64decode(full_base64)
                session.raw_text = content_bytes.decode('utf-8', errors='ignore')
                
                # Limpiar
                session.raw_text = clean_irc_codes(session.raw_text)
                session.total_lines = len(session.raw_text.split('\n'))
                
                # Estimar preguntas
                estimated = len(re.findall(r'Pregunta:\s*\d+\s*/\s*\d+', session.raw_text))
                
                response.update({
                    "message": "Todos los chunks recibidos y decodificados",
                    "total_lines": session.total_lines,
                    "estimated_questions": estimated,
                    "next_step": f"POST /process_session con session_id: {request.session_id}"
                })
                
                # Liberar memoria de chunks base64
                session.base64_chunks = []
                
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Error decodificando: {str(e)}")
        else:
            response["next_step"] = "Continúa enviando chunks con /append_base64"
        
        return JSONResponse(response)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)[:200]}")

@app.post("/process_session")
async def process_session(request: ProcessSessionRequest):
    """Procesa el texto completo y extrae las preguntas"""
    if request.session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions_storage[request.session_id]
    
    if not session.raw_text:
        raise HTTPException(status_code=400, detail="No hay texto para procesar. Asegúrate de enviar todos los chunks primero")
    
    try:
        session.last_access = datetime.now()
        
        # Extraer preguntas
        session.questions = extract_questions_from_text(session.raw_text)
        session.processed = True
        
        # Estadísticas
        categories_count = {}
        for q in session.questions:
            if q['categoria']:
                categories_count[q['categoria']] = categories_count.get(q['categoria'], 0) + 1
        
        # Detectar equipos
        equipos = []
        if 'FOGUETES' in session.raw_text[:2000]:
            equipos.append('FOGUETES')
        if 'LIDERES' in session.raw_text[:2000] or 'LÍDERES' in session.raw_text[:2000]:
            equipos.append('LIDERES')
        
        return JSONResponse({
            "session_id": request.session_id,
            "total_questions": len(session.questions),
            "categories": categories_count,
            "equipos": equipos,
            "message": f"Procesadas {len(session.questions)} preguntas",
            "next_step": f"GET /get_questions/{request.session_id}/1/5"
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando: {str(e)[:200]}")

@app.get("/get_questions/{session_id}/{start}/{end}")
async def get_questions(session_id: str, start: int, end: int):
    """Devuelve un rango de preguntas"""
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions_storage[session_id]
    
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

def cleanup_old_sessions():
    """Limpia sesiones de más de 2 horas"""
    cutoff = datetime.now() - timedelta(hours=2)
    expired = [sid for sid, s in sessions_storage.items() 
              if s.created_at < cutoff]
    for sid in expired:
        del sessions_storage[sid]

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "9.0.0",
        "status": "active",
        "sessions": len(sessions_storage),
        "endpoints": {
            "base64_chunked": [
                "POST /init_base64_session - Inicia sesión con primer chunk",
                "POST /append_base64 - Añade más chunks base64",
                "POST /process_session - Procesa el texto completo",
                "GET /get_questions/{id}/{start}/{end} - Obtiene preguntas"
            ]
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "sessions": len(sessions_storage)}
