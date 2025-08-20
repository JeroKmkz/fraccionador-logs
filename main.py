from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
import json
from typing import List, Dict, Any, Optional
import uvicorn
import gc
import codecs

app = FastAPI(title="Trivial IRC Log Processor", version="3.1.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def limpiar_log_irclog_avanzado(text: str) -> str:
    """Limpiador avanzado que maneja códigos IRC en múltiples formatos"""
    # PASO 1: Convertir códigos unicode escapados a caracteres reales
    try:
        text = codecs.decode(text, 'unicode_escape')
    except:
        pass
    
    # PASO 2: Patrones de limpieza IRC
    patterns = {
        'color': re.compile(r'\\x03\\d{0,2}(?:,\\d{1,2})?'),
        'bold': re.compile(r'\\x02'),
        'italic': re.compile(r'\\x1D'),
        'underline': re.compile(r'\\x1F'),
        'reset': re.compile(r'\\x0F'),
        'delete': re.compile(r'\\x7F'),
        'color_coords': re.compile(r'\\b\\d{1,2},\\d{1,2}\\b'),
        'controls': re.compile(r'[\\x00-\\x08\\x0B-\\x0C\\x0E-\\x1F]'),
        'spaces': re.compile(r'\\s{2,}'),
    }
    
    # PASO 3: Aplicar limpieza línea por línea
    lines = text.split('\\n')
    cleaned_lines = []
    
    for line in lines:
        cleaned = line
        for pattern in patterns.values():
            cleaned = pattern.sub(' ', cleaned)
        cleaned = re.sub(r'\\s+', ' ', cleaned.strip())
        cleaned_lines.append(cleaned)
    
    return '\\n'.join(cleaned_lines)

def detect_questions_advanced(lines: List[str]) -> List[Dict]:
    """Detección avanzada de preguntas con más contexto"""
    questions = []
    
    for i, line in enumerate(lines):
        line_lower = line.lower()
        
        if 'la buena:' in line_lower or 'las buenas:' in line_lower:
            # Extraer respuesta
            if 'la buena:' in line_lower:
                start_pos = line_lower.find('la buena:') + 9
            else:
                start_pos = line_lower.find('las buenas:') + 11
            
            end_pos = line_lower.find('mandada por', start_pos)
            if end_pos == -1:
                answer_text = line[start_pos:].strip()
            else:
                answer_text = line[start_pos:end_pos].strip()
            
            # Limpiar respuesta
            answer_clean = re.sub(r'\\d+,\\d+', '', answer_text)
            answer_clean = re.sub(r'\\s+', ' ', answer_clean).strip()
            
            if answer_clean:
                # Buscar contexto anterior (pregunta)
                question_context = ""
                question_line = ""
                for j in range(max(0, i-15), i):
                    prev_line = lines[j]
                    prev_line_lower = prev_line.lower()
                    
                    # Buscar líneas que contengan preguntas
                    if any(word in prev_line_lower for word in ['pregunta:', '¿', '?']) and len(prev_line.strip()) > 20:
                        question_line = prev_line.strip()
                        # Limpiar la pregunta también
                        question_context = limpiar_log_irclog_avanzado(question_line)
                        break
                
                # Buscar quién mandó la pregunta
                author = ""
                mandada_match = re.search(r'mandada por[:\\s]+([^\\s,]+)', line_lower)
                if mandada_match:
                    author = mandada_match.group(1).upper()
                
                # Buscar número de pregunta
                question_number = len(questions) + 1
                if question_context:
                    num_match = re.search(r'pregunta[:\\s]+(\\d+)', question_context.lower())
                    if num_match:
                        question_number = int(num_match.group(1))
                
                questions.append({
                    'number': question_number,
                    'line_index': i,
                    'answer': answer_clean,
                    'question_context': question_context[:300] if question_context else "",
                    'author': author,
                    'raw_line': line[:200]
                })
    
    return questions

def find_participants(lines: List[str]) -> List[str]:
    """Encuentra los participantes del juego"""
    participants = set()
    
    for line in lines:
        # Buscar nicks después de timestamps
        match = re.match(r'\\d+:\\d+:\\d+.*?<([^>]+)>', line)
        if match:
            nick = match.group(1)
            # Excluir bots y servidores comunes
            if nick not in ['Saga_Noren', 'VegaSicilia', 'Bot', 'Server', 'GleviBot']:
                participants.add(nick)
        
        # Buscar en "mandada por"
        mandada_match = re.search(r'mandada por[:\\s]+([^\\s,]+)', line.lower())
        if mandada_match:
            author = mandada_match.group(1).upper()
            if author not in ['FIREBALL', 'CASTRO', 'BOT']:
                participants.add(author)
    
    return sorted(list(participants))

def build_narrative_blocks(questions: List[Dict], participants: List[str], total_lines: int) -> Dict[str, Any]:
    """Construye bloques narrativos con respuesta limitada a 12 preguntas para evitar ResponseTooLargeError"""
    
    if not questions:
        return {
            "status": "no_questions",
            "total_questions": 0,
            "total_lines": total_lines,
            "participants": participants,
            "blocks": [],
            "message": "No se encontraron preguntas en el log"
        }
    
    # Limitar a máximo 12 preguntas por respuesta
    limited_questions = questions[:12]
    remaining_questions = len(questions) - 12
    
    # Dividir en bloques de máximo 4 preguntas cada uno
    block_size = 4
    blocks = []
    
    for i in range(0, len(limited_questions), block_size):
        block_questions = limited_questions[i:i + block_size]
        
        block = {
            "block_number": len(blocks) + 1,
            "question_range": [block_questions[0]['number'], block_questions[-1]['number']],
            "questions": []
        }
        
        for q in block_questions:
            # Limitar el contexto para reducir tamaño
            context_short = q['question_context'][:100] if q['question_context'] else ""
            
            block["questions"].append({
                "number": q['number'],
                "answer": q['answer'][:100],  # Limitar respuesta a 100 chars
                "author": q['author'],
                "context": context_short
            })
        
        blocks.append(block)
    
    return {
        "status": "success",
        "total_questions": len(questions),
        "total_lines": total_lines,
        "participants": participants[:10],  # Limitar participantes
        "blocks": blocks,
        "summary": {
            "game_info": f"Partida con {len(questions)} preguntas y {len(participants)} participantes",
            "blocks_created": len(blocks),
            "showing_first": len(limited_questions),
            "remaining_questions": remaining_questions if remaining_questions > 0 else 0
        }
    }

@app.post("/process_direct")
async def process_direct(request: Request):
    """Endpoint único que procesa todo el log de una vez"""
    try:
        body = await request.body()
        raw_text = body.decode('utf-8', errors='ignore')
        
        print(f"DEBUG: Recibido texto de {len(raw_text)} caracteres")
        print(f"DEBUG: Primeras 200 chars: {raw_text[:200]}")
        
        if not raw_text.strip():
            return {
                "status": "error",
                "error": "Contenido vacío"
            }
        
        # PASO 1: Limpiar códigos IRC
        cleaned_text = limpiar_log_irclog_avanzado(raw_text)
        lines = cleaned_text.split('\\n')
        
        print(f"DEBUG: Después de limpiar: {len(lines)} líneas")
        
        # PASO 2: Detectar preguntas
        questions = detect_questions_advanced(lines)
        
        print(f"DEBUG: Preguntas detectadas: {len(questions)}")
        
        # PASO 3: Encontrar participantes
        participants = find_participants(lines)
        
        print(f"DEBUG: Participantes encontrados: {len(participants)}")
        
        # PASO 4: Construir bloques narrativos
        result = build_narrative_blocks(questions, participants, len(lines))
        
        # Añadir información de procesamiento
        result["processing_info"] = {
            "original_length": len(raw_text),
            "cleaned_length": len(cleaned_text),
            "lines_processed": len(lines),
            "irc_codes_removed": len(raw_text) - len(cleaned_text)
        }
        
        return result
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "debug_info": f"Error procesando log: {str(e)}"
        }

@app.post("/process_file")
async def process_file(file: UploadFile = File(...)):
    """Endpoint específico para procesar archivos subidos"""
    try:
        print(f"DEBUG: Recibido archivo {file.filename}, tipo: {file.content_type}")
        
        # Leer contenido del archivo
        content = await file.read()
        
        print(f"DEBUG: Archivo leído, {len(content)} bytes")
        
        # Intentar diferentes encodings
        raw_text = ""
        encodings = ['utf-8', 'latin-1', 'cp1252', 'iso-8859-1']
        
        for encoding in encodings:
            try:
                raw_text = content.decode(encoding, errors='ignore')
                print(f"DEBUG: Decodificado exitosamente con {encoding}")
                break
            except:
                continue
        
        if not raw_text.strip():
            return {
                "status": "error",
                "error": f"No se pudo leer el contenido del archivo {file.filename}"
            }
        
        print(f"DEBUG: Texto decodificado: {len(raw_text)} caracteres")
        print(f"DEBUG: Primeras 200 chars: {raw_text[:200]}")
        
        # Procesar con la misma lógica que process_direct
        cleaned_text = limpiar_log_irclog_avanzado(raw_text)
        lines = cleaned_text.split('\\n')
        questions = detect_questions_advanced(lines)
        participants = find_participants(lines)
        result = build_narrative_blocks(questions, participants, len(lines))
        
        result["filename"] = file.filename
        result["processing_info"] = {
            "original_length": len(raw_text),
            "cleaned_length": len(cleaned_text),
            "lines_processed": len(lines),
            "irc_codes_removed": len(raw_text) - len(cleaned_text)
        }
        
        return result
        
    except Exception as e:
        print(f"ERROR procesando archivo: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "status": "error",
            "error": str(e),
            "filename": file.filename if file else "unknown"
        }

@app.post("/process_file_continue")
async def process_file_continue(request: Request):
    """Continúa procesando desde una pregunta específica"""
    try:
        body = await request.body()
        
        # Limpiar el cuerpo antes de parsear JSON
        body_text = body.decode('utf-8', errors='ignore')
        
        # Limpiar caracteres de control que rompen JSON
        import json
        # Primero intentar parsear directo
        try:
            data = json.loads(body_text)
        except json.JSONDecodeError:
            # Si falla, limpiar caracteres problemáticos
            cleaned_body = re.sub(r'[\\x00-\\x1F\\x7F]', ' ', body_text)  # Quitar caracteres de control
            cleaned_body = re.sub(r'[""''´`]', '"', cleaned_body)      # Normalizar comillas
            cleaned_body = re.sub(r'\\s+', ' ', cleaned_body)          # Normalizar espacios
            try:
                data = json.loads(cleaned_body)
            except:
                return {"status": "error", "error": "No se pudo parsear el JSON"}
        
        raw_text = data.get('text', '')
        start_question = data.get('start_question', 13)
        
        if not raw_text.strip():
            return {"status": "error", "error": "Contenido vacío"}
        
        print(f"DEBUG: Continuando desde pregunta {start_question}")
        
        # Procesar texto (ya limpio)
        cleaned_text = limpiar_log_irclog_avanzado(raw_text)
        lines = cleaned_text.split('\\n')
        all_questions = detect_questions_advanced(lines)
        participants = find_participants(lines)
        
        print(f"DEBUG: Total preguntas encontradas: {len(all_questions)}")
        
        # Tomar solo las preguntas desde start_question
        questions_subset = [q for q in all_questions if q['number'] >= start_question]
        limited_questions = questions_subset[:12]  # Máximo 12 más
        
        print(f"DEBUG: Preguntas en este bloque: {len(limited_questions)}")
        
        # Crear bloques
        blocks = []
        block_size = 4
        
        for i in range(0, len(limited_questions), block_size):
            block_questions = limited_questions[i:i + block_size]
            
            block = {
                "block_number": len(blocks) + 1,
                "question_range": [block_questions[0]['number'], block_questions[-1]['number']],
                "questions": []
            }
            
            for q in block_questions:
                context_short = q['question_context'][:100] if q['question_context'] else ""
                block["questions"].append({
                    "number": q['number'],
                    "answer": q['answer'][:100],
                    "author": q['author'],
                    "context": context_short
                })
            
            blocks.append(block)
        
        remaining = len(all_questions) - start_question - len(limited_questions) + 1
        
        return {
            "status": "continued",
            "total_questions": len(all_questions),
            "showing_range": [start_question, start_question + len(limited_questions) - 1] if limited_questions else [start_question, start_question],
            "blocks": blocks,
            "remaining_questions": remaining if remaining > 0 else 0
        }
        
    except Exception as e:
        print(f"ERROR en process_file_continue: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": "error", "error": str(e)}

# Endpoints de utilidad
@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API v3.1 - Con Soporte de Archivos", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "3.1.0"}

@app.get("/test_sample")
async def test_sample():
    """Test con muestra del log real"""
    sample = """23:01:17'276 <VegaSicilia> 0,1 Pregunta: 0,4 2 / 350,14 Base Datos Preguntas: 12,15 TrivialIrc
23:01:19'086 <VegaSicilia> 3,8 GASTRONOMÍA0,1 LICOR DE COLOR AMARILLO Y CONSISTENCIA ESPESA, PREPARADO CON YEMAS DE HUEVO, VAINILLA, CANELA, ALMENDRA MOLIDA, LECHE Y ALGÚN TIPO DE ALCOHOL, ORIGINARIO DE MÉXICO.4,0 ( 1 palabra )
23:01:34'407 <VegaSicilia> 2,0 La buena: 0,4 ROMPOPE2,0 Mandada por: ^CASTRO^"""
    
    # Procesarlo
    cleaned = limpiar_log_irclog_avanzado(sample)
    lines = cleaned.split('\\n')
    questions = detect_questions_advanced(lines)
    participants = find_participants(lines)
    
    return {
        "sample_text": sample,
        "cleaned_text": cleaned,
        "questions_found": len(questions),
        "questions": questions,
        "participants": participants,
        "processing_works": len(questions) > 0
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

