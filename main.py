from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import uuid
from typing import List, Dict, Optional
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="7.0.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento de sesiones
sessions = {}

class LogSession:
    def __init__(self):
        self.lines = []
        self.questions = []
        self.created_at = datetime.now()
        self.last_access = datetime.now()
        self.processed = False

class InitRequest(BaseModel):
    """Inicia una nueva sesión de procesamiento"""
    first_chunk: str  # Primer trozo del log

class AppendRequest(BaseModel):
    """Añade más líneas a una sesión existente"""
    session_id: str
    chunk: str  # Siguiente trozo del log

class ProcessRequest(BaseModel):
    """Procesa el log completo ya cargado"""
    session_id: str

def clean_irc_line(line: str) -> str:
    """Limpia una línea de códigos IRC"""
    # Eliminar códigos de color IRC
    line = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', line)
    line = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', line)
    # Limpiar patrones de color numéricos al inicio
    line = re.sub(r'^\d+,\d+\s*', '', line)
    line = re.sub(r'\s+\d+,\d+\s+', ' ', line)
    return line.strip()

def parse_questions(lines: List[str]) -> List[Dict]:
    """Extrae las preguntas del log"""
    questions = []
    current_q = None
    
    for i, line in enumerate(lines):
        clean_line = clean_irc_line(line)
        
        # Detectar nueva pregunta
        pregunta_match = re.search(r'Pregunta:\s*(\d+)\s*/\s*(\d+)', clean_line)
        if pregunta_match:
            if current_q:
                questions.append(current_q)
            
            current_q = {
                'numero': int(pregunta_match.group(1)),
                'total': int(pregunta_match.group(2)),
                'categoria': '',
                'pregunta': '',
                'linea_inicio': i,
                'linea_fin': i,
                'ganador': '',
                'respuesta': '',
                'participantes': []
            }
            continue
            
        if current_q:
            # Actualizar línea final
            current_q['linea_fin'] = i
            
            # Detectar categoría y pregunta
            categorias = ['MEDICINA-SALUD', 'GASTRONOMÍA', 'INFORMÁTICA', 'DEPORTE', 
                         'HISTORIA', 'GEOGRAFÍA', 'CIENCIAS', 'ARTE', 'CINE', 'MÚSICA',
                         'LITERATURA', 'TELEVISIÓN', 'POLÍTICA', 'ECONOMÍA']
            
            for cat in categorias:
                if cat in clean_line and not current_q['categoria']:
                    current_q['categoria'] = cat
                    # Extraer texto de la pregunta
                    parts = clean_line.split(cat)
                    if len(parts) > 1:
                        pregunta_text = parts[-1]
                        # Limpiar indicador de palabras
                        pregunta_text = re.sub(r'\([^)]*palabras?\)', '', pregunta_text)
                        current_q['pregunta'] = pregunta_text.strip()
                    break
            
            # Detectar ganador (primer acierto)
            if '>>>' in clean_line and not current_q['ganador']:
                if 'scratchea' not in clean_line and ' a ' in clean_line:
                    ganador_match = re.search(r'>>>(\w+)', clean_line)
                    if ganador_match:
                        current_q['ganador'] = ganador_match.group(1)
            
            # Detectar participantes
            if '>>>' in clean_line:
                player_match = re.search(r'>>>(\w+)', clean_line)
                if player_match and player_match.group(1) not in current_q['participantes']:
                    current_q['participantes'].append(player_match.group(1))
            
            # Detectar respuesta correcta
            if 'La buena:' in clean_line or 'Las buenas:' in clean_line:
                respuesta_match = re.search(r'(?:La buena:|Las buenas:)\s*([^]+?)(?:Mandada por:|$)', clean_line)
                if respuesta_match:
                    current_q['respuesta'] = respuesta_match.group(1).strip()
    
    # Añadir última pregunta
    if current_q:
        questions.append(current_q)
    
    return questions

@app.post("/init_session")
async def init_session(request: InitRequest):
    """Inicia una nueva sesión y carga el primer chunk"""
    try:
        session_id = str(uuid.uuid4())[:8]
        session = LogSession()
        
        # Procesar primer chunk
        lines = request.first_chunk.strip().split('\n')
        session.lines.extend(lines)
        
        sessions[session_id] = session
        
        # Limpiar sesiones viejas
        cutoff = datetime.now() - timedelta(hours=2)
        expired = [sid for sid, s in sessions.items() if s.created_at < cutoff]
        for sid in expired:
            del sessions[sid]
        
        return {
            "session_id": session_id,
            "lines_received": len(lines),
            "total_lines": len(session.lines),
            "message": "Sesión iniciada. Usa /append para añadir más líneas o /process para procesar."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/append")
async def append_chunk(request: AppendRequest):
    """Añade más líneas a una sesión existente"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    try:
        session = sessions[request.session_id]
        session.last_access = datetime.now()
        
        # Añadir nuevas líneas
        lines = request.chunk.strip().split('\n')
        session.lines.extend(lines)
        
        return {
            "session_id": request.session_id,
            "lines_added": len(lines),
            "total_lines": len(session.lines),
            "message": "Líneas añadidas. Continúa con /append o usa /process para procesar."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process")
async def process_log(request: ProcessRequest):
    """Procesa el log completo y extrae las preguntas"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    try:
        session = sessions[request.session_id]
        session.last_access = datetime.now()
        
        # Procesar todas las líneas
        session.questions = parse_questions(session.lines)
        session.processed = True
        
        # Resumen
        categorias_count = {}
        for q in session.questions:
            if q['categoria']:
                categorias_count[q['categoria']] = categorias_count.get(q['categoria'], 0) + 1
        
        return {
            "session_id": request.session_id,
            "total_lines": len(session.lines),
            "total_questions": len(session.questions),
            "questions_range": f"1-{len(session.questions)}",
            "categorias": categorias_count,
            "message": f"Procesadas {len(session.questions)} preguntas. Usa /get_questions para obtenerlas."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_questions/{session_id}/{start}/{end}")
async def get_questions(session_id: str, start: int, end: int):
    """Obtiene un rango de preguntas procesadas"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions[session_id]
    session.last_access = datetime.now()
    
    if not session.processed:
        raise HTTPException(status_code=400, detail="Log no procesado. Usa /process primero")
    
    # Validar rango
    start_idx = start - 1  # Convertir a índice base 0
    end_idx = min(end, len(session.questions))
    
    if start_idx < 0 or start_idx >= len(session.questions):
        raise HTTPException(status_code=400, detail="Rango inválido")
    
    # Obtener preguntas y sus líneas asociadas
    result_questions = []
    for q in session.questions[start_idx:end_idx]:
        # Incluir las líneas relevantes para contexto
        context_lines = session.lines[q['linea_inicio']:min(q['linea_fin']+3, len(session.lines))]
        
        result_questions.append({
            "numero": q['numero'],
            "categoria": q['categoria'],
            "pregunta": q['pregunta'],
            "ganador": q['ganador'],
            "respuesta": q['respuesta'],
            "participantes_count": len(q['participantes']),
            "lineas_contexto": [clean_irc_line(l) for l in context_lines[:10]]  # Máx 10 líneas
        })
    
    return {
        "session_id": session_id,
        "questions": result_questions,
        "returned": f"{start}-{end_idx}",
        "total": len(session.questions),
        "has_more": end_idx < len(session.questions),
        "next_range": f"{end_idx+1}-{min(end_idx+5, len(session.questions))}" if end_idx < len(session.questions) else None
    }

@app.get("/get_raw_lines/{session_id}/{start}/{count}")
async def get_raw_lines(session_id: str, start: int, count: int):
    """Obtiene líneas crudas del log (útil para debug)"""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions[session_id]
    session.last_access = datetime.now()
    
    start_idx = max(0, start - 1)
    end_idx = min(start_idx + count, len(session.lines))
    
    lines = session.lines[start_idx:end_idx]
    
    return {
        "session_id": session_id,
        "lines": [clean_irc_line(l) for l in lines],
        "returned": f"{start_idx+1}-{end_idx}",
        "total_lines": len(session.lines)
    }

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "7.0.0",
        "status": "active",
        "sessions": len(sessions),
        "instructions": {
            "1": "POST /init_session con first_chunk",
            "2": "POST /append para añadir más chunks (opcional)",
            "3": "POST /process para procesar todo",
            "4": "GET /get_questions/{session_id}/{start}/{end} para obtener preguntas"
        }
    }

@app.get("/health")
async def health():
    active_sessions = len(sessions)
    total_lines = sum(len(s.lines) for s in sessions.values())
    
    return {
        "status": "healthy",
        "sessions": active_sessions,
        "total_lines_cached": total_lines
    }
