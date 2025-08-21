from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import re
import uuid
import base64
from typing import List, Dict, Optional
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="11.0.0")

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
        self.full_text = ""
        self.question_blocks = []
        self.total_questions = 0
        self.metadata = {}
        self.processed = False

class UploadLogRequest(BaseModel):
    content_base64: str
    filename: Optional[str] = "log.txt"

def clean_irc_codes(text: str) -> str:
    """Limpia colores, timestamps y nicks"""
    # Eliminar códigos de color IRC
    text = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', text)
    # Eliminar otros códigos de control
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    # Eliminar timestamps y nicks tipo: 23:00:36''976 <Usuario>
    text = re.sub(r'^\d{2}:\d{2}:\d{2}.*?>\s*', '', text, flags=re.MULTILINE)
    return text.strip()

def extract_and_chunk_questions(text: str, questions_per_block: int = 5) -> List[List[Dict]]:
    lines = text.split('\n')
    all_questions = []
    current_q = None
    
    for i, line in enumerate(lines):
        clean_line = line.strip()
        
        # Detectar inicio de pregunta
        match = re.search(r'Pregunta[:\s]+(\d+)\s*/\s*(\d+)', clean_line, re.IGNORECASE)
        if match:
            if current_q and current_q.get('pregunta'):
                all_questions.append(current_q)
            current_q = {
                'numero': int(match.group(1)),
                'total': int(match.group(2)),
                'categoria': '',
                'pregunta': '',
                'ganador': '',
                'respuesta': '',
                'tiempo': '',
                'participantes': [],
                'linea_inicio': i
            }
            continue

        if current_q:
            # Categoría + pregunta
            if not current_q['pregunta']:
                cat_match = re.match(r'([A-ZÁÉÍÓÚÜÑ\- ]+)\s+(.+)', clean_line)
                if cat_match:
                    current_q['categoria'] = cat_match.group(1).strip()
                    current_q['pregunta'] = cat_match.group(2).strip()
            
            # Ganador
            if '>>>' in clean_line and 'scratchea' not in clean_line.lower():
                ganador_match = re.search(r'>>>(\w+)', clean_line)
                if ganador_match and not current_q['ganador']:
                    current_q['ganador'] = ganador_match.group(1)
                    # Extraer tiempo opcional
                    tiempo_match = re.search(r'(\d+)[\'"`](\d+)', clean_line)
                    if tiempo_match:
                        current_q['tiempo'] = f"{tiempo_match.group(1)}.{tiempo_match.group(2)}s"
            
            # Respuesta correcta
            resp_match = re.search(r'(?:La buena|Las buenas|Respuesta correcta|La respuesta es):\s*(.+?)(?:Mandada por:|$)', clean_line, re.IGNORECASE)
            if resp_match:
                current_q['respuesta'] = resp_match.group(1).strip()
    
    if current_q and current_q.get('pregunta'):
        all_questions.append(current_q)

    # Dividir en bloques de N
    blocks = []
    for i in range(0, len(all_questions), questions_per_block):
        blocks.append(all_questions[i:i + questions_per_block])
    return blocks

@app.post("/upload_complete_log")
async def upload_complete_log(request: UploadLogRequest):
    try:
        content_bytes = base64.b64decode(request.content_base64)
        text = content_bytes.decode('utf-8', errors='ignore')
        if not text:
            raise HTTPException(status_code=400, detail="Contenido vacío")
        
        text = clean_irc_codes(text)
        session_id = str(uuid.uuid4())[:8]
        session = SessionData(session_id)
        session.full_text = text
        session.question_blocks = extract_and_chunk_questions(text)
        session.total_questions = sum(len(b) for b in session.question_blocks)
        session.processed = True

        # Detectar equipos
        equipos = []
        if 'FOGUETES' in text.upper():
            equipos.append('FOGUETES')
        if 'LIDERES' in text.upper() or 'LÍDERES' in text.upper():
            equipos.append('LIDERES')
        session.metadata['equipos'] = equipos

        sessions_storage[session_id] = session
        cleanup_old_sessions()
        
        return JSONResponse({
            "session_id": session_id,
            "status": "success",
            "total_questions": session.total_questions,
            "total_blocks": len(session.question_blocks),
            "questions_per_block": 5,
            "equipos": equipos,
            "message": f"Log procesado con {session.total_questions} preguntas, en {len(session.question_blocks)} bloques",
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando: {str(e)[:500]}")

@app.get("/get_block/{session_id}/{block_number}")
async def get_block(session_id: str, block_number: int):
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    session = sessions_storage[session_id]
    if not session.processed:
        raise HTTPException(status_code=400, detail="Sesión no procesada")
    if block_number < 1 or block_number > len(session.question_blocks):
        raise HTTPException(status_code=400, detail=f"Bloque inválido (1-{len(session.question_blocks)})")
    block = session.question_blocks[block_number-1]
    start_q = (block_number - 1) * 5 + 1
    end_q = start_q + len(block) - 1
    return JSONResponse({
        "session_id": session_id,
        "block_number": block_number,
        "questions_range": f"{start_q}-{end_q}",
        "questions": block,
        "has_more": block_number < len(session.question_blocks)
    })

def cleanup_old_sessions():
    cutoff = datetime.now() - timedelta(hours=3)
    for sid in [sid for sid, s in sessions_storage.items() if s.created_at < cutoff]:
        del sessions_storage[sid]

@app.get("/debug_session/{session_id}")
async def debug_session(session_id: str):
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    session = sessions_storage[session_id]
    lines = session.full_text.split('\n')
    potential = []
    for i, line in enumerate(lines[:100]):
        if 'pregunta' in line.lower() or '>>>' in line or 'buena' in line.lower():
            potential.append({"line_num": i, "content": line[:120]})
    return {
        "session_id": session_id,
        "total_lines": len(lines),
        "potential_questions": potential,
        "sample": session.full_text[:500]
    }

@app.get("/")
async def root():
    return {"service": "Trivial Chunker API", "version": "11.0.0", "status": "active"}

@app.get("/health")
async def health():
    return {"status": "healthy", "sessions": len(sessions_storage)}

