from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import re
import uuid
import base64
from typing import List, Dict, Optional
from datetime import datetime, timedelta

app = FastAPI(title="Trivial Chunker API", version="10.0.0")

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
        self.full_text = ""  # Texto completo limpio
        self.question_blocks = []  # Bloques de 5 preguntas cada uno
        self.total_questions = 0
        self.metadata = {}
        self.processed = False

class UploadLogRequest(BaseModel):
    """Recibe el log completo en base64"""
    content_base64: str
    filename: Optional[str] = "log.txt"

class GetBlockRequest(BaseModel):
    """Solicita un bloque específico de preguntas"""
    session_id: str
    block_number: int  # 1, 2, 3, etc.

def clean_irc_codes(text: str) -> str:
    """Limpia códigos IRC del texto"""
    # Eliminar códigos de color IRC
    text = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', text)
    # Eliminar otros códigos de control
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    # Limpiar patrones numéricos de color
    text = re.sub(r'(?:^|\s)\d+,\d+\s+', ' ', text)
    return text.strip()

def extract_and_chunk_questions(text: str, questions_per_block: int = 5) -> List[List[Dict]]:
    """
    Extrae todas las preguntas y las divide en bloques de N preguntas
    """
    lines = text.split('\n')
    all_questions = []
    current_q = None
    
    for i, line in enumerate(lines):
        # Primero limpiamos la línea
        clean_line = clean_irc_codes(line)
        
        # Detectar nueva pregunta - PATRÓN MEJORADO
        # Busca variaciones como "Pregunta: 1 / 35" o similares
        pregunta_patterns = [
            r'Pregunta:\s*(\d+)\s*/\s*(\d+)',
            r'Pregunta\s*:\s*(\d+)\s*/\s*(\d+)',
            r'Pregunta\s+(\d+)\s*/\s*(\d+)',
            r'pregunta:\s*(\d+)\s*/\s*(\d+)'
        ]
        
        pregunta_match = None
        for pattern in pregunta_patterns:
            pregunta_match = re.search(pattern, clean_line, re.IGNORECASE)
            if pregunta_match:
                break
        
        if pregunta_match:
            # Guardar pregunta anterior si existe
            if current_q and current_q.get('pregunta'):
                all_questions.append(current_q)
            
            # Iniciar nueva pregunta
            current_q = {
                'numero': int(pregunta_match.group(1)),
                'total': int(pregunta_match.group(2)),
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
            # Detectar categoría y texto de la pregunta
            categorias = [
                'MEDICINA-SALUD', 'MEDICINA', 'SALUD',
                'GASTRONOMÍA', 'GASTRONOMIA',
                'INFORMÁTICA', 'INFORMATICA', 'TECNOLOGÍA', 'TECNOLOGIA',
                'DEPORTE', 'DEPORTES', 'FÚTBOL', 'FUTBOL',
                'HISTORIA', 'GEOGRAFÍA', 'GEOGRAFIA',
                'CIENCIAS', 'CIENCIA', 'FÍSICA', 'FISICA', 'QUÍMICA', 'QUIMICA',
                'ARTE', 'CINE', 'MÚSICA', 'MUSICA',
                'LITERATURA', 'TELEVISIÓN', 'TELEVISION', 'TV',
                'POLÍTICA', 'POLITICA', 'ECONOMÍA', 'ECONOMIA',
                'MISCELÁNEA', 'MISCELANEA', 'CULTURA'
            ]
            
            # Si encontramos una categoría y aún no tenemos pregunta
            if not current_q['pregunta']:
                for cat in categorias:
                    if cat in clean_line.upper():
                        current_q['categoria'] = cat
                        # El texto de la pregunta suele estar después de la categoría
                        # Buscar el texto después de la categoría
                        idx = clean_line.upper().find(cat)
                        if idx != -1:
                            pregunta_text = clean_line[idx + len(cat):]
                            # Limpiar indicadores de palabras
                            pregunta_text = re.sub(r'\([^)]*palabras?\)', '', pregunta_text)
                            pregunta_text = re.sub(r'^\s*[-:]\s*', '', pregunta_text)
                            pregunta_text = pregunta_text.strip()
                            if pregunta_text and len(pregunta_text) > 5:  # Solo si hay contenido real
                                current_q['pregunta'] = pregunta_text
                                break
            
            # Detectar ganador (cuando alguien acierta)
            if '>>>' in line:  # Usar línea original para detectar >>>
                # Patrón típico: ">>>JUGADOR a 01''23" o ">>>JUGADOR scratchea"
                if 'scratchea' not in line.lower():
                    ganador_match = re.search(r'>>>(\w+)', line)
                    if ganador_match and not current_q['ganador']:
                        current_q['ganador'] = ganador_match.group(1)
                        # Intentar extraer tiempo
                        tiempo_match = re.search(r'(\d+)[\'"`](\d+)', line)
                        if tiempo_match:
                            current_q['tiempo'] = f"{tiempo_match.group(1)}.{tiempo_match.group(2)}s"
                
                # Añadir a participantes
                player_match = re.search(r'>>>(\w+)', line)
                if player_match:
                    player = player_match.group(1)
                    if player not in current_q['participantes']:
                        current_q['participantes'].append(player)
            
            # Detectar respuesta correcta
            respuesta_patterns = [
                r'La buena:\s*([^]+?)(?:Mandada por:|$)',
                r'Las buenas:\s*([^]+?)(?:Mandada por:|$)',
                r'Respuesta correcta:\s*([^]+?)(?:Mandada por:|$)',
                r'La respuesta es:\s*([^]+?)(?:Mandada por:|$)'
            ]
            
            for pattern in respuesta_patterns:
                respuesta_match = re.search(pattern, clean_line, re.IGNORECASE)
                if respuesta_match:
                    current_q['respuesta'] = respuesta_match.group(1).strip()
                    break
    
    # Añadir última pregunta si existe
    if current_q and current_q.get('pregunta'):
        all_questions.append(current_q)
    
    # Si no encontramos preguntas con el método anterior, intentar método alternativo
    if len(all_questions) == 0:
        # Buscar cualquier línea que contenga "Pregunta" y un número
        for i, line in enumerate(lines):
            if 'pregunta' in line.lower() and re.search(r'\d+\s*/\s*\d+', line):
                # Extraer información básica
                nums = re.search(r'(\d+)\s*/\s*(\d+)', line)
                if nums:
                    q = {
                        'numero': int(nums.group(1)),
                        'total': int(nums.group(2)),
                        'categoria': 'DESCONOCIDA',
                        'pregunta': f'Pregunta {nums.group(1)}',
                        'ganador': '',
                        'respuesta': '',
                        'tiempo': '',
                        'participantes': [],
                        'linea': i
                    }
                    all_questions.append(q)
    
    # Dividir en bloques
    blocks = []
    for i in range(0, len(all_questions), questions_per_block):
        blocks.append(all_questions[i:i + questions_per_block])
    
    return blocks

@app.post("/upload_complete_log")
async def upload_complete_log(request: UploadLogRequest):
    """
    PASO 1: Recibe el log completo, lo procesa y lo trocea en bloques
    El servidor hace todo el trabajo pesado
    """
    try:
        # Validar que hay contenido
        if not request.content_base64:
            raise HTTPException(status_code=400, detail="No se recibió contenido")
        
        # Decodificar base64
        try:
            # Eliminar posibles espacios o saltos de línea en el base64
            clean_base64 = request.content_base64.replace('\n', '').replace('\r', '').replace(' ', '')
            content_bytes = base64.b64decode(clean_base64)
            
            # Intentar decodificar con varios encodings
            text = None
            for encoding in ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']:
                try:
                    text = content_bytes.decode(encoding)
                    break
                except:
                    continue
            
            if not text:
                text = content_bytes.decode('utf-8', errors='ignore')
                
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error decodificando base64: {str(e)}")
        
        # Validar que el texto tiene contenido sustancial
        lines = text.split('\n')
        if len(lines) < 50:
            # Si hay muy pocas líneas, puede ser un error
            sample = '\n'.join(lines[:10]) if len(lines) >= 10 else text
            raise HTTPException(
                status_code=400, 
                detail=f"El archivo parece demasiado corto ({len(lines)} líneas). Primeras líneas: {sample[:500]}"
            )
        
        # Limpiar códigos IRC PERO conservar estructura
        cleaned_lines = []
        for line in lines:
            # Eliminar solo los códigos de control, no el contenido
            clean = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', line)
            clean = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', clean)
            cleaned_lines.append(clean)
        
        text = '\n'.join(cleaned_lines)
        
        # Generar session_id
        session_id = str(uuid.uuid4())[:8]
        
        # Crear sesión
        session = SessionData(session_id)
        session.full_text = text
        
        # Extraer y trocear preguntas en bloques de 5
        session.question_blocks = extract_and_chunk_questions(text, questions_per_block=5)
        session.total_questions = sum(len(block) for block in session.question_blocks)
        session.processed = True
        
        # Metadatos
        session.metadata = {
            'filename': request.filename,
            'total_lines': len(lines),
            'original_size': len(content_bytes),
            'total_blocks': len(session.question_blocks),
            'questions_per_block': 5
        }
        
        # Detectar equipos
        equipos = []
        text_start = text[:5000] if len(text) > 5000 else text
        if 'FOGUETES' in text_start.upper():
            equipos.append('FOGUETES')
        if 'LIDERES' in text_start.upper() or 'LÍDERES' in text_start.upper():
            equipos.append('LIDERES')
        session.metadata['equipos'] = equipos
        
        # Guardar sesión
        sessions_storage[session_id] = session
        
        # Limpiar sesiones viejas
        cleanup_old_sessions()
        
        # Preparar respuesta detallada
        response_data = {
            "session_id": session_id,
            "status": "success",
            "total_questions": session.total_questions,
            "total_blocks": len(session.question_blocks),
            "questions_per_block": 5,
            "equipos": equipos,
            "total_lines": len(lines),
            "message": f"Log procesado: {len(lines)} líneas, {session.total_questions} preguntas detectadas"
        }
        
        if session.total_questions == 0:
            # Si no se detectaron preguntas, dar información de debug
            sample_lines = []
            for i, line in enumerate(lines[:50]):
                if 'pregunta' in line.lower() or '>>>' in line:
                    sample_lines.append(f"Línea {i}: {line[:100]}")
            
            response_data["warning"] = "No se detectaron preguntas. Verifica el formato del log."
            response_data["debug_info"] = {
                "sample_lines": sample_lines[:10],
                "pregunta_mentions": text.lower().count('pregunta'),
                "arrow_marks": text.count('>>>'),
                "first_500_chars": text[:500]
            }
        else:
            response_data["instructions"] = f"Usa /get_block/{session_id}/1 para obtener el primer bloque"
        
        return JSONResponse(response_data)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando: {str(e)[:500]}")

@app.get("/get_block/{session_id}/{block_number}")
async def get_block(session_id: str, block_number: int):
    """
    PASO 2+: Obtiene un bloque específico de preguntas
    El usuario puede pedir bloques según necesite
    """
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o expirada")
    
    session = sessions_storage[session_id]
    session.last_access = datetime.now()
    
    if not session.processed:
        raise HTTPException(status_code=400, detail="Sesión no procesada")
    
    # Validar número de bloque
    if block_number < 1 or block_number > len(session.question_blocks):
        raise HTTPException(status_code=400, detail=f"Bloque inválido. Debe estar entre 1 y {len(session.question_blocks)}")
    
    # Obtener el bloque (índice base 0)
    block = session.question_blocks[block_number - 1]
    
    # Calcular rango de preguntas
    start_q = (block_number - 1) * 5 + 1
    end_q = start_q + len(block) - 1
    
    return JSONResponse({
        "session_id": session_id,
        "block_number": block_number,
        "total_blocks": len(session.question_blocks),
        "questions_range": f"{start_q}-{end_q}",
        "questions": block,
        "has_more": block_number < len(session.question_blocks),
        "next_block": block_number + 1 if block_number < len(session.question_blocks) else None,
        "message": f"Bloque {block_number} de {len(session.question_blocks)}"
    })

@app.get("/session_info/{session_id}")
async def session_info(session_id: str):
    """
    Obtiene información general de la sesión sin las preguntas
    """
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions_storage[session_id]
    
    # Calcular estadísticas
    stats = {
        'total_questions': session.total_questions,
        'total_blocks': len(session.question_blocks),
        'questions_per_block': 5,
        'equipos': session.metadata.get('equipos', []),
        'filename': session.metadata.get('filename', 'unknown'),
        'total_lines': session.metadata.get('total_lines', 0)
    }
    
    # Top jugadores si está procesado
    if session.processed:
        ganadores = {}
        for block in session.question_blocks:
            for q in block:
                if q['ganador']:
                    ganadores[q['ganador']] = ganadores.get(q['ganador'], 0) + 1
        
        top_3 = sorted(ganadores.items(), key=lambda x: x[1], reverse=True)[:3]
        stats['top_players'] = [{'player': p[0], 'wins': p[1]} for p in top_3]
    
    return JSONResponse({
        "session_id": session_id,
        "status": "ready",
        "statistics": stats,
        "available_blocks": list(range(1, len(session.question_blocks) + 1)),
        "instructions": f"Usa /get_block/{session_id}/N para obtener el bloque N (1-{len(session.question_blocks)})"
    })

def cleanup_old_sessions():
    """Limpia sesiones de más de 3 horas"""
    cutoff = datetime.now() - timedelta(hours=3)
    expired = [sid for sid, s in sessions_storage.items() 
              if s.created_at < cutoff]
    for sid in expired:
        del sessions_storage[sid]

@app.get("/debug_session/{session_id}")
async def debug_session(session_id: str):
    """
    Endpoint de DEBUG para ver qué está pasando con el texto
    """
    if session_id not in sessions_storage:
        raise HTTPException(status_code=404, detail="Sesión no encontrada")
    
    session = sessions_storage[session_id]
    
    # Buscar líneas que parezcan preguntas
    lines = session.full_text.split('\n')
    potential_questions = []
    
    for i, line in enumerate(lines[:100]):  # Primeras 100 líneas
        if 'pregunta' in line.lower() or '>>>' in line or 'buena:' in line.lower():
            potential_questions.append({
                'line_num': i,
                'content': line[:100]  # Primeros 100 chars
            })
    
    # Buscar patrones específicos
    pregunta_count = len(re.findall(r'Pregunta[:\s]+\d+\s*/\s*\d+', session.full_text, re.IGNORECASE))
    categoria_count = len(re.findall(r'(MEDICINA|GASTRONOMÍA|DEPORTE|HISTORIA)', session.full_text, re.IGNORECASE))
    
    return JSONResponse({
        "session_id": session_id,
        "total_lines": len(lines),
        "first_10_lines": lines[:10],
        "potential_questions": potential_questions[:20],
        "pattern_counts": {
            "pregunta_pattern": pregunta_count,
            "categoria_pattern": categoria_count,
            ">>> marks": session.full_text.count('>>>'),
            "La buena": session.full_text.count('La buena')
        },
        "text_sample": session.full_text[:500]
    })

@app.get("/")
async def root():
    return {
        "service": "Trivial Chunker API",
        "version": "10.0.0",
        "status": "active",
        "active_sessions": len(sessions_storage),
        "description": "Sistema de procesamiento de logs de Trivial IRC con troceado automático en servidor",
        "workflow": {
            "step1": "POST /upload_complete_log - Sube el log completo en base64",
            "step2": "GET /session_info/{session_id} - Obtiene información de la sesión",
            "step3": "GET /get_block/{session_id}/{N} - Obtiene el bloque N de preguntas"
        }
    }

@app.get("/health")
async def health():
    total_questions = sum(s.total_questions for s in sessions_storage.values())
    return {
        "status": "healthy",
        "active_sessions": len(sessions_storage),
        "total_questions_stored": total_questions
    }
