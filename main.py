from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import uuid
from typing import List, Dict, Optional
import asyncio
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="5.0.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento en memoria con TTL
file_storage = {}

class FileSession:
    def __init__(self, content: str, questions: List[Dict]):
        self.content = content
        self.questions = questions
        self.created_at = datetime.now()
        self.last_accessed = datetime.now()
        
class ProcessResponse(BaseModel):
    session_id: str
    total_questions: int
    questions_batch: List[Dict]
    batch_number: int
    total_batches: int
    has_more: bool

def limpiar_log_irc(text: bytes) -> str:
    """Limpia códigos IRC del texto binario"""
    try:
        # Decodificar ignorando errores
        text_str = text.decode('utf-8', errors='ignore')
    except:
        text_str = text.decode('latin-1', errors='ignore')
    
    # Eliminar códigos de color IRC
    text_str = re.sub(b'\x03\d{0,2}(?:,\d{1,2})?'.decode('utf-8', errors='ignore'), '', text_str)
    text_str = re.sub(b'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]'.decode('utf-8', errors='ignore'), '', text_str)
    
    # Limpiar patrones de color restantes
    text_str = re.sub(r'(?:^|\s)\d+,\d+\s+', ' ', text_str)
    
    return text_str

def extract_all_questions(text: str) -> List[Dict]:
    """Extrae TODAS las preguntas del log de una vez"""
    lines = text.split('\n')
    questions = []
    current_q = None
    
    for i, line in enumerate(lines):
        # Detectar nueva pregunta
        pregunta_match = re.search(r'Pregunta:\s*(\d+)\s*/\s*(\d+)', line)
        if pregunta_match:
            if current_q and current_q.get('pregunta'):  # Solo guardar si tiene contenido
                questions.append(current_q)
            
            current_q = {
                'numero': int(pregunta_match.group(1)),
                'total': int(pregunta_match.group(2)),
                'categoria': '',
                'pregunta': '',
                'respuestas': [],
                'ganador': None,
                'respuesta_correcta': '',
                'tiempo': ''
            }
            continue
            
        if current_q:
            # Extraer hora
            if not current_q['tiempo']:
                tiempo_match = re.match(r'^(\d{2}:\d{2}:\d{2})', line)
                if tiempo_match:
                    current_q['tiempo'] = tiempo_match.group(1)
            
            # Detectar categoría y pregunta
            categorias = ['MEDICINA-SALUD', 'GASTRONOMÍA', 'INFORMÁTICA', 'DEPORTE', 
                         'HISTORIA', 'GEOGRAFÍA', 'CIENCIAS', 'ARTE', 'CINE', 'MÚSICA',
                         'LITERATURA', 'TELEVISIÓN', 'POLÍTICA', 'ECONOMÍA']
            
            for cat in categorias:
                if cat in line and not current_q['pregunta']:
                    current_q['categoria'] = cat
                    # Extraer pregunta después de la categoría
                    pregunta_text = re.split(cat, line)[-1]
                    # Limpiar pregunta
                    pregunta_text = re.sub(r'\([^)]*palabras?\)', '', pregunta_text).strip()
                    current_q['pregunta'] = pregunta_text
                    break
            
            # Detectar respuestas de jugadores (cuando alguien acierta)
            if '>>>' in line and 'scratchea' not in line and ' a ' in line:
                player_match = re.search(r'>>>(\w+)', line)
                tiempo_match = re.search(r'(\d+)[\'"](\d+)', line)
                if player_match:
                    respuesta = {
                        'jugador': player_match.group(1),
                        'tiempo': f"{tiempo_match.group(1)}.{tiempo_match.group(2)}" if tiempo_match else None
                    }
                    current_q['respuestas'].append(respuesta)
                    if not current_q['ganador']:
                        current_q['ganador'] = player_match.group(1)
            
            # Detectar respuesta correcta
            if 'La buena:' in line or 'Las buenas:' in line:
                respuesta_match = re.search(r'(?:La buena:|Las buenas:)\s*([^]+?)(?:Mandada por:|$)', line)
                if respuesta_match:
                    current_q['respuesta_correcta'] = respuesta_match.group(1).strip()
    
    # Agregar última pregunta si existe
    if current_q and current_q.get('pregunta'):
        questions.append(current_q)
    
    return questions

@app.post("/process_file_complete")
async def process_file_complete(file: UploadFile = File(...)):
    """Procesa el archivo completo y lo almacena en memoria"""
    try:
        # Leer archivo completo
        content = await file.read()
        
        # Limpiar el contenido
        cleaned_text = limpiar_log_irc(content)
        
        # Extraer TODAS las preguntas
        all_questions = extract_all_questions(cleaned_text)
        
        if not all_questions:
            raise HTTPException(status_code=400, detail="No se detectaron preguntas en el archivo")
        
        # Generar ID de sesión
        session_id = str(uuid.uuid4())
        
        # Almacenar TODO en memoria
        file_storage[session_id] = FileSession(cleaned_text, all_questions)
        
        # Limpiar sesiones antiguas (más de 1 hora)
        cutoff_time = datetime.now() - timedelta(hours=1)
        expired_sessions = [sid for sid, session in file_storage.items() 
                          if session.created_at < cutoff_time]
        for sid in expired_sessions:
            del file_storage[sid]
        
        # Preparar primera respuesta con batch de 12 preguntas
        batch_size = 12
        first_batch = all_questions[:batch_size]
        total_batches = (len(all_questions) + batch_size - 1) // batch_size
        
        return ProcessResponse(
            session_id=session_id,
            total_questions=len(all_questions),
            questions_batch=first_batch,
            batch_number=1,
            total_batches=total_batches,
            has_more=len(all_questions) > batch_size
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando archivo: {str(e)}")

@app.get("/get_batch/{session_id}/{batch_number}")
async def get_batch(session_id: str, batch_number: int):
    """Obtiene un batch específico de preguntas de la sesión"""
    if session_id not in file_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    
    session = file_storage[session_id]
    session.last_accessed = datetime.now()
    
    batch_size = 12
    total_questions = len(session.questions)
    total_batches = (total_questions + batch_size - 1) // batch_size
    
    if batch_number < 1 or batch_number > total_batches:
        raise HTTPException(status_code=400, detail=f"Batch inválido. Debe estar entre 1 y {total_batches}")
    
    # Calcular índices
    start_idx = (batch_number - 1) * batch_size
    end_idx = min(start_idx + batch_size, total_questions)
    
    questions_batch = session.questions[start_idx:end_idx]
    
    return ProcessResponse(
        session_id=session_id,
        total_questions=total_questions,
        questions_batch=questions_batch,
        batch_number=batch_number,
        total_batches=total_batches,
        has_more=batch_number < total_batches
    )

@app.get("/get_all_questions/{session_id}")
async def get_all_questions(session_id: str):
    """Obtiene TODAS las preguntas de una vez (para GPTs con más memoria)"""
    if session_id not in file_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    
    session = file_storage[session_id]
    session.last_accessed = datetime.now()
    
    return {
        "session_id": session_id,
        "total_questions": len(session.questions),
        "all_questions": session.questions
    }

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "5.0.0",
        "status": "active",
        "active_sessions": len(file_storage),
        "endpoints": [
            "POST /process_file_complete - Procesa archivo completo",
            "GET /get_batch/{session_id}/{batch_number} - Obtiene batch específico",
            "GET /get_all_questions/{session_id} - Obtiene todas las preguntas",
            "GET /health - Estado del servicio"
        ]
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "sessions_active": len(file_storage),
        "memory_usage": sum(len(s.content) for s in file_storage.values())
    }
