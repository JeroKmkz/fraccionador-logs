from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import re
import base64
from typing import List, Dict, Optional
import json
import uuid

app = FastAPI(title="Trivial Chunker API", version="4.0.0")

# CORS para permitir llamadas desde ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Almacenamiento temporal de sesiones (en producción usar Redis)
sessions = {}

class ProcessRequest(BaseModel):
    content_base64: str
    session_id: Optional[str] = None
    
class ContinueRequest(BaseModel):
    session_id: str
    from_question: int

class ProcessResponse(BaseModel):
    session_id: str
    total_questions: int
    current_batch: Dict
    has_more: bool
    next_question: Optional[int]

def limpiar_log_irc(text: str) -> str:
    """Limpia completamente los códigos IRC del texto"""
    # Eliminar códigos de color IRC (\x03 seguido de números)
    text = re.sub(r'\x03\d{1,2}(?:,\d{1,2})?', '', text)
    # Eliminar otros códigos de control IRC
    text = re.sub(r'[\x00-\x1F\x7F]', '', text)
    # Limpiar marcadores de color restantes
    text = re.sub(r'\d+,\d+\s*', '', text)
    return text

def extract_question_block(lines: List[str], start_idx: int, end_idx: int) -> Dict:
    """Extrae información de un bloque de preguntas"""
    questions = []
    current_q = None
    
    for i in range(start_idx, min(end_idx, len(lines))):
        line = lines[i]
        
        # Detectar nueva pregunta
        pregunta_match = re.search(r'Pregunta:\s*(\d+)\s*/\s*(\d+)', line)
        if pregunta_match:
            if current_q:
                questions.append(current_q)
            current_q = {
                'numero': int(pregunta_match.group(1)),
                'total': int(pregunta_match.group(2)),
                'categoria': '',
                'pregunta': '',
                'respuestas': [],
                'ganador': '',
                'respuesta_correcta': ''
            }
            continue
            
        if current_q:
            # Detectar categoría y pregunta
            if 'MEDICINA' in line or 'GASTRONOMÍA' in line or 'INFORMÁTICA' in line or 'DEPORTE' in line:
                parts = re.split(r'(?:MEDICINA-SALUD|GASTRONOMÍA|INFORMÁTICA|DEPORTE)', line)
                if len(parts) > 1:
                    categoria_match = re.search(r'(MEDICINA-SALUD|GASTRONOMÍA|INFORMÁTICA|DEPORTE)', line)
                    if categoria_match:
                        current_q['categoria'] = categoria_match.group(1)
                    current_q['pregunta'] = parts[-1].strip()
                    
            # Detectar respuestas de jugadores
            elif '>>>' in line and 'scratchea' not in line:
                player_match = re.search(r'>>>(\w+)', line)
                if player_match:
                    current_q['respuestas'].append(player_match.group(1))
                    
            # Detectar ganador y respuesta correcta
            elif 'La buena:' in line:
                respuesta_match = re.search(r'La buena:\s*([^]+?)(?:Mandada por:|$)', line)
                if respuesta_match:
                    current_q['respuesta_correcta'] = respuesta_match.group(1).strip()
                if current_q['respuestas']:
                    current_q['ganador'] = current_q['respuestas'][0]
    
    if current_q:
        questions.append(current_q)
        
    return {
        'questions': questions,
        'from_question': questions[0]['numero'] if questions else start_idx,
        'to_question': questions[-1]['numero'] if questions else end_idx
    }

@app.post("/process_base64", response_model=ProcessResponse)
async def process_base64(request: ProcessRequest):
    """Procesa el log enviado en base64"""
    try:
        # Decodificar base64
        decoded_bytes = base64.b64decode(request.content_base64)
        text = decoded_bytes.decode('utf-8', errors='ignore')
        
        # Limpiar el texto
        text = limpiar_log_irc(text)
        lines = text.split('\n')
        
        # Detectar todas las preguntas
        question_indices = []
        for i, line in enumerate(lines):
            if re.search(r'Pregunta:\s*\d+\s*/\s*\d+', line):
                question_indices.append(i)
        
        total_questions = len(question_indices)
        
        # Crear o recuperar sesión
        session_id = request.session_id or str(uuid.uuid4())
        
        # Guardar datos de sesión
        sessions[session_id] = {
            'lines': lines,
            'question_indices': question_indices,
            'total_questions': total_questions
        }
        
        # Procesar primer batch (primeras 10 preguntas)
        batch_size = 10
        end_idx = question_indices[batch_size] if len(question_indices) > batch_size else len(lines)
        
        current_batch = extract_question_block(lines, 0, end_idx)
        
        return ProcessResponse(
            session_id=session_id,
            total_questions=total_questions,
            current_batch=current_batch,
            has_more=total_questions > batch_size,
            next_question=batch_size + 1 if total_questions > batch_size else None
        )
        
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error procesando el contenido: {str(e)}")

@app.post("/continue_session", response_model=ProcessResponse)
async def continue_session(request: ContinueRequest):
    """Continúa procesando desde una pregunta específica"""
    if request.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions[request.session_id]
    lines = session['lines']
    question_indices = session['question_indices']
    total_questions = session['total_questions']
    
    # Calcular índices para el batch solicitado
    batch_size = 10
    start_q = request.from_question - 1  # Convertir a índice base 0
    end_q = min(start_q + batch_size, total_questions)
    
    if start_q >= total_questions:
        raise HTTPException(status_code=400, detail="Número de pregunta fuera de rango")
    
    start_idx = question_indices[start_q]
    end_idx = question_indices[end_q] if end_q < total_questions else len(lines)
    
    current_batch = extract_question_block(lines, start_idx, end_idx)
    
    return ProcessResponse(
        session_id=request.session_id,
        total_questions=total_questions,
        current_batch=current_batch,
        has_more=end_q < total_questions,
        next_question=end_q + 1 if end_q < total_questions else None
    )

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "4.0.0",
        "status": "active",
        "endpoints": [
            "POST /process_base64 - Procesa log en base64",
            "POST /continue_session - Continúa procesando desde pregunta X",
            "GET /health - Estado del servicio"
        ]
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "sessions_active": len(sessions)}
