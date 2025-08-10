from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
from typing import List, Dict, Any
import uvicorn

app = FastAPI(title="Trivial IRC Log Processor", version="2.0.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def limpiar_log_irclog_avanzado(text: str) -> str:
    """
    Limpiador avanzado basado en IRCLogCleaner
    Elimina códigos de color, formato y caracteres especiales de IRC
    """
    import re
    
    # Patrones basados en el código del usuario
    patterns = {
        # Códigos de color (\x03 seguido de 1-2 dígitos, opcionalmente coma y 1-2 dígitos más)
        'color': re.compile(r'\x03\d{1,2}(?:,\d{1,2})?'),
        
        # Negrita (\x02)
        'bold': re.compile(r'\x02'),
        
        # Cursiva (\x1D)
        'italic': re.compile(r'\x1D'),
        
        # Subrayado (\x1F)
        'underline': re.compile(r'\x1F'),
        
        # Reset de formato (\x0F)
        'reset': re.compile(r'\x0F'),
        
        # Carácter de borrado (\x7F)
        'delete': re.compile(r'\x7F'),
        
        # Códigos de color alternativos (como 2,9 o 11,1)
        'color_coords': re.compile(r'\b\d{1,2},\d{1,2}\b'),
        
        # Secuencias de escape ANSI
        'ansi': re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'),
        
        # Múltiples espacios
        'multiple_spaces': re.compile(r'\s{2,}'),
        
        # Casos específicos para limpiar caracteres residuales al inicio
        'inicio_residual': re.compile(r'^[:\?]\s*'),
        
        # Patrones adicionales para códigos unicode que envía ChatGPT
        'unicode_controls': re.compile(r'\\u[0-9a-fA-F]{4}'),
        'escaped_controls': re.compile(r'\\x[0-9a-fA-F]{2}'),
    }
    
    # Limpiar línea por línea
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        if not isinstance(line, str):
            cleaned_lines.append("")
            continue
            
        try:
            cleaned = line
            
            # Aplicar todos los patrones de limpieza
            cleaned = patterns['color'].sub('', cleaned)
            cleaned = patterns['bold'].sub('', cleaned)
            cleaned = patterns['italic'].sub('', cleaned)
            cleaned = patterns['underline'].sub('', cleaned)
            cleaned = patterns['reset'].sub('', cleaned)
            cleaned = patterns['delete'].sub('', cleaned)
            cleaned = patterns['ansi'].sub('', cleaned)
            cleaned = patterns['color_coords'].sub('', cleaned)
            cleaned = patterns['unicode_controls'].sub('', cleaned)
            cleaned = patterns['escaped_controls'].sub('', cleaned)
            cleaned = patterns['multiple_spaces'].sub(' ', cleaned)
            cleaned = patterns['inicio_residual'].sub('', cleaned)
            
            # Limpiar espacios al inicio y final
            cleaned = cleaned.strip()
            cleaned_lines.append(cleaned)
            
        except Exception as e:
            print(f"Error limpiando línea: {e}")
            cleaned_lines.append(line.strip())
    
    return '\n'.join(cleaned_lines)

def detect_question_indices(lines: List[str]) -> List[Dict]:
    """Detecta índices de preguntas por líneas con 'La(s) buena(s)'"""
    questions = []
    
    for i, line in enumerate(lines):
        # Buscar simplemente "La buena:" o "Las buenas:"
        line_lower = line.lower()
        
        if 'la buena:' in line_lower or 'las buenas:' in line_lower:
            print(f"DEBUG línea {i}: {repr(line[:100])}")
            
            # Extraer respuesta de forma simple
            if 'la buena:' in line_lower:
                start = line_lower.find('la buena:') + 9  # len("la buena:")
            else:
                start = line_lower.find('las buenas:') + 11  # len("las buenas:")
            
            # Buscar hasta "mandada por" o final de línea
            end_pos = line_lower.find('mandada por', start)
            if end_pos == -1:
                answer_part = line[start:].strip()
            else:
                answer_part = line[start:end_pos].strip()
            
            # Limpiar respuesta de códigos residuales
            answer = re.sub(r'\d+,\d+', '', answer_part)  # Quitar códigos como "2,0"
            answer = re.sub(r'\s+', ' ', answer).strip()
            
            if answer:
                print(f"DEBUG: Respuesta encontrada: {repr(answer)}")
                questions.append({
                    'idx': len(questions) + 1,
                    'line_index': i,
                    'answer': answer
                })
    
    print(f"DEBUG: Total preguntas detectadas: {len(questions)}")
    return questions

def build_blocks(raw_text: str) -> Dict[str, Any]:
    """Construye los bloques divididos por preguntas"""
    lines = raw_text.split('\n')
    questions = detect_question_indices(lines)
    
    if not questions:
        return {
            "filename": "",
            "total_questions": 0,
            "total_lines": len(lines),
            "blocks": [],
            "debug_info": f"Procesadas {len(lines)} líneas, no se encontraron respuestas"
        }
    
    # Dividir en máximo 5 bloques equilibrados
    total_questions = len(questions)
    num_blocks = min(5, total_questions)
    base_size, remainder = divmod(total_questions, num_blocks)
    
    blocks = []
    start_line = 0
    q_start = 0
    
    for block_num in range(num_blocks):
        # Calcular cuántas preguntas van en este bloque
        block_size = base_size + (1 if block_num < remainder else 0)
        q_end = q_start + block_size
        
        # Línea final del bloque (incluye la línea de "La buena" de la última pregunta)
        end_line = questions[q_end - 1]['line_index']
        
        # Construir preguntas del bloque
        block_questions = []
        for q_idx in range(q_start, q_end):
            question = questions[q_idx]
            
            # Determinar rango de líneas para esta pregunta
            q_start_line = questions[q_idx - 1]['line_index'] + 1 if q_idx > 0 else start_line
            q_end_line = question['line_index']
            
            # Texto exacto de la pregunta
            question_lines = lines[q_start_line:q_end_line + 1]
            question_text = '\n'.join(question_lines)
            
            block_questions.append({
                "idx": question['idx'],
                "answer": question['answer'],
                "line_range": [q_start_line, q_end_line],
                "text_raw": question_text,
                "text_clean": limpiar_log_irclog_avanzado(question_text)
            })
        
        # Texto completo del bloque
        block_lines = lines[start_line:end_line + 1]
        block_text = '\n'.join(block_lines)
        
        blocks.append({
            "block": block_num + 1,
            "q_index_range": [questions[q_start]['idx'], questions[q_end - 1]['idx']],
            "line_range": [start_line, end_line],
            "questions": block_questions,
            "text_raw": block_text,
            "text_clean": limpiar_log_irclog_avanzado(block_text)
        })
        
        # Preparar para siguiente bloque
        start_line = end_line + 1
        q_start = q_end
    
    return {
        "filename": "",
        "total_questions": total_questions,
        "total_lines": len(lines),
        "blocks": blocks
    }

async def load_text_from_upload(upload: UploadFile) -> str:
    """Carga texto desde archivo subido (.txt o .cfg)"""
    content = await upload.read()
    
    # Verificar extensión
    if not (upload.filename.lower().endswith('.txt') or upload.filename.lower().endswith('.cfg')):
        raise HTTPException(400, "Solo se aceptan archivos .txt o .cfg")
    
    try:
        return content.decode('utf-8', errors='ignore')
    except Exception as e:
        raise HTTPException(400, f"Error decodificando archivo: {str(e)}")

@app.post("/debug_lines")
async def debug_lines(file: UploadFile = File(...)):
    """Debug: ver líneas que contienen 'buena'"""
    try:
        content = await file.read()
        text_content = content.decode('utf-8', errors='ignore')
        
        # Limpiar
        cleaned = limpiar_log_irclog_avanzado(text_content)
        lines = cleaned.split('\n')
        
        # Buscar líneas con "buena"
        buena_lines = []
        for i, line in enumerate(lines):
            if 'buena' in line.lower():
                buena_lines.append({
                    "line_number": i,
                    "content": line,
                    "length": len(line)
                })
        
        return {
            "filename": file.filename,
            "total_lines": len(lines),
            "lines_with_buena": buena_lines[:10],  # Primeras 10
            "total_buena_lines": len(buena_lines)
        }
        
    except Exception as e:
        raise HTTPException(500, f"Error: {str(e)}")

@app.post("/clean_log")
async def clean_log(request: Request):
    """Action 1: Limpia códigos IRC del texto usando manejo robusto"""
    try:
        # Leer el contenido con máxima tolerancia
        body = await request.body()
        
        # Intentar diferentes métodos de decodificación
        try:
            text_content = body.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text_content = body.decode('latin-1')
            except:
                text_content = body.decode('utf-8', errors='replace')
        
        # Si el contenido parece estar escapado como JSON, intentar parsearlo
        if text_content.startswith('{"') and '"text":' in text_content:
            try:
                import json
                parsed = json.loads(text_content)
                if 'text' in parsed:
                    text_content = parsed['text']
            except:
                pass
        
        # Limpiar secuencias de escape unicode que vienen de ChatGPT
        import codecs
        try:
            # Decodificar secuencias \uXXXX
            text_content = codecs.decode(text_content, 'unicode_escape')
        except:
            pass
        
        if not text_content.strip():
            return {
                "status": "error",
                "error": "Contenido vacío después de decodificación",
                "cleaned_text": "",
                "question_lines_found": 0
            }
        
        print(f"DEBUG: Recibido texto de {len(text_content)} caracteres")
        print(f"DEBUG: Primeros 100 chars: {repr(text_content[:100])}")
        
        # Limpieza con algoritmo avanzado
        cleaned = limpiar_log_irclog_avanzado(text_content)
        
        # Verificar que mantenemos las líneas importantes
        lines = cleaned.split('\n')
        buena_lines = [i for i, line in enumerate(lines) if 'La buena:' in line.lower() or 'Las buenas:' in line.lower()]
        
        print(f"DEBUG: Después de limpiar: {len(lines)} líneas, {len(buena_lines)} con respuestas")
        
        return {
            "status": "cleaned",
            "original_length": len(text_content),
            "cleaned_length": len(cleaned), 
            "total_lines": len(lines),
            "question_lines_found": len(buena_lines),
            "cleaned_text": cleaned,
            "preview_first_200": cleaned[:200],
            "preview_last_200": cleaned[-200:] if len(cleaned) > 200 else "",
            "debug_original_start": repr(text_content[:50])
        }
        
    except Exception as e:
        print(f"ERROR en clean_log: {str(e)}")
        return {
            "status": "error",
            "error": str(e),
            "cleaned_text": "",
            "question_lines_found": 0
        }

@app.post("/process")
async def process_file(file: UploadFile = File(...)):
    """Procesa archivo subido (.txt o .cfg)"""
    try:
        text_content = await load_text_from_upload(file)
        result = build_blocks(text_content)
        result["filename"] = file.filename
        return result
    
    except Exception as e:
        raise HTTPException(500, f"Error procesando archivo: {str(e)}")

@app.post("/process_text_plain")
async def process_text_plain(request: Request):
    """Action 2: Procesa texto limpio directamente desde el body"""
    try:
        # Leer el contenido raw del body
        body = await request.body()
        text_content = body.decode('utf-8', errors='ignore')
        
        if not text_content.strip():
            raise HTTPException(400, "Contenido vacío")
        
        print(f"DEBUG: Procesando texto limpio de {len(text_content.split(chr(10)))} líneas")
        
        result = build_blocks(text_content)
        result["filename"] = "log_procesado.txt"
        
        print(f"DEBUG: Resultado: {result['total_questions']} preguntas")
        
        return result
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(500, f"Error procesando texto: {str(e)}")

@app.post("/process_file_direct")
async def process_file_direct(file: UploadFile = File(...)):
    """Procesa archivo directamente sin pasar por ChatGPT"""
    try:
        # Leer contenido del archivo
        content = await file.read()
        text_content = content.decode('utf-8', errors='ignore')
        
        print(f"DEBUG: Archivo {file.filename}, {len(text_content)} caracteres")
        
        # PASO 1: Limpiar
        cleaned = limpiar_log_irclog_avanzado(text_content)
        lines = cleaned.split('\n')
        buena_lines = [i for i, line in enumerate(lines) if 'La buena:' in line.lower() or 'Las buenas:' in line.lower()]
        
        print(f"DEBUG: Limpieza: {len(lines)} líneas, {len(buena_lines)} preguntas")
        
        # PASO 2: Procesar bloques
        if len(buena_lines) > 0:
            result = build_blocks(cleaned)
            result["filename"] = file.filename
            
            # Añadir información de limpieza
            result["cleaning_info"] = {
                "original_length": len(text_content),
                "cleaned_length": len(cleaned),
                "questions_found": len(buena_lines)
            }
            
            return result
        else:
            return {
                "filename": file.filename,
                "total_questions": 0,
                "total_lines": len(lines),
                "blocks": [],
                "error": "No se encontraron preguntas en el archivo",
                "cleaning_info": {
                    "original_length": len(text_content),
                    "cleaned_length": len(cleaned),
                    "questions_found": 0
                }
            }
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(500, f"Error procesando archivo: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API v2.0", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/test_sample")
async def test_sample():
    """Test con muestra del log real"""
    sample = """23:02:07'921 <Saga_Noren> 2,0 La buena: 0,4 AMENA2,0 Mandada por: ADRASTEA
23:02:35'697 <Saga_Noren> 2,0 Las buenas: 0,4 VIRTUAL PRIVATE NETWORK, RED PRIVADA VIRTUAL2,0 Mandada por: CORT"""
    
    # Primero limpiar
    cleaned = limpiar_log_irclog_avanzado(sample)
    
    # Luego detectar preguntas
    lines = cleaned.split('\n')
    questions = detect_question_indices(lines)
    
    return {
        "original_sample": sample,
        "cleaned_sample": cleaned,
        "detected_questions": questions,
        "cleaning_worked": len(questions) > 0
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)




