from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
from typing import List, Dict, Any
import uvicorn
import gc
import codecs

app = FastAPI(title="Trivial IRC Log Processor", version="2.1.0")

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
    Limpiador avanzado que maneja códigos IRC en múltiples formatos
    """
    import re
    
    # PASO 1: Convertir códigos unicode escapados a caracteres reales
    try:
        # Decodificar secuencias como \\u0003 a caracteres reales
        text = codecs.decode(text, 'unicode_escape')
    except:
        pass
    
    # PASO 2: Patrones de limpieza IRC
    patterns = {
        # Códigos de color básicos
        'color': re.compile(r'\x03\d{0,2}(?:,\d{1,2})?'),
        'bold': re.compile(r'\x02'),
        'italic': re.compile(r'\x1D'),
        'underline': re.compile(r'\x1F'),
        'reset': re.compile(r'\x0F'),
        'delete': re.compile(r'\x7F'),
        
        # Códigos de color sueltos como "2,0" 
        'color_coords': re.compile(r'\b\d{1,2},\d{1,2}\b'),
        
        # Otros caracteres de control
        'controls': re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]'),
        
        # Múltiples espacios
        'spaces': re.compile(r'\s{2,}'),
    }
    
    # PASO 3: Aplicar limpieza línea por línea
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        cleaned = line
        
        # Aplicar todos los patrones
        for pattern in patterns.values():
            cleaned = pattern.sub(' ', cleaned)
        
        # Normalizar espacios
        cleaned = re.sub(r'\s+', ' ', cleaned.strip())
        cleaned_lines.append(cleaned)
    
    return '\n'.join(cleaned_lines)

def detect_question_indices_simple(lines: List[str]) -> List[Dict]:
    """Detección súper simple de preguntas"""
    questions = []
    
    try:
        for i, line in enumerate(lines):
            line_lower = line.lower()
            
            # Buscar patrones de respuesta
            if 'la buena:' in line_lower or 'las buenas:' in line_lower:
                print(f"DEBUG línea {i}: {line[:100]}")
                
                # Extraer respuesta
                if 'la buena:' in line_lower:
                    start_pos = line_lower.find('la buena:') + 9
                else:
                    start_pos = line_lower.find('las buenas:') + 11
                
                # Buscar final
                end_pos = line_lower.find('mandada por', start_pos)
                if end_pos == -1:
                    answer_text = line[start_pos:].strip()
                else:
                    answer_text = line[start_pos:end_pos].strip()
                
                # Limpiar respuesta
                answer_clean = re.sub(r'\d+,\d+', '', answer_text)
                answer_clean = re.sub(r'\s+', ' ', answer_clean).strip()
                
                if answer_clean:
                    questions.append({
                        'idx': len(questions) + 1,
                        'line_index': i,
                        'answer': answer_clean
                    })
                    print(f"DEBUG respuesta: {answer_clean}")
    
    except Exception as e:
        print(f"ERROR en detección: {e}")
    
    print(f"DEBUG: Total detectadas: {len(questions)}")
    return questions

def build_blocks_safe(raw_text: str) -> Dict[str, Any]:
    """Construye bloques de forma segura"""
    try:
        lines = raw_text.split('\n')
        questions = detect_question_indices_simple(lines)
        
        if not questions:
            return {
                "filename": "",
                "total_questions": 0,
                "total_lines": len(lines),
                "blocks": [],
                "debug_info": f"Procesadas {len(lines)} líneas, no se encontraron respuestas"
            }
        
        # Dividir en máximo 5 bloques
        total_questions = len(questions)
        num_blocks = min(5, total_questions)
        base_size, remainder = divmod(total_questions, num_blocks)
        
        blocks = []
        start_line = 0
        q_start = 0
        
        for block_num in range(num_blocks):
            block_size = base_size + (1 if block_num < remainder else 0)
            q_end = q_start + block_size
            
            end_line = questions[q_end - 1]['line_index']
            
            # Construir preguntas del bloque
            block_questions = []
            for q_idx in range(q_start, q_end):
                question = questions[q_idx]
                
                q_start_line = questions[q_idx - 1]['line_index'] + 1 if q_idx > 0 else start_line
                q_end_line = question['line_index']
                
                question_lines = lines[q_start_line:q_end_line + 1]
                question_text = '\n'.join(question_lines)
                
                block_questions.append({
                    "idx": question['idx'],
                    "answer": question['answer'],
                    "line_range": [q_start_line, q_end_line],
                    "text_raw": question_text[:1000],
                    "text_clean": question_text[:1000]
                })
            
            # Texto del bloque
            block_lines = lines[start_line:end_line + 1]
            block_text = '\n'.join(block_lines)
            
            blocks.append({
                "block": block_num + 1,
                "q_index_range": [questions[q_start]['idx'], questions[q_end - 1]['idx']],
                "line_range": [start_line, end_line],
                "questions": block_questions,
                "text_raw": block_text[:2000] if len(block_text) <= 2000 else block_text[:2000] + "...[truncado]"
            })
            
            start_line = end_line + 1
            q_start = q_end
        
        return {
            "filename": "",
            "total_questions": total_questions,
            "total_lines": len(lines),
            "blocks": blocks
        }
        
    except Exception as e:
        print(f"ERROR en build_blocks: {e}")
        return {
            "filename": "",
            "total_questions": 0,
            "total_lines": 0,
            "blocks": [],
            "error": str(e)
        }

@app.post("/count_lines")
async def count_lines(file: UploadFile = File(...)):
    """Solo cuenta líneas sin procesar nada pesado"""
    try:
        print(f"DEBUG: Iniciando count_lines para {file.filename}")
        
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        
        # Buscar líneas con "buena" en las primeras 100 líneas
        buena_samples = []
        buena_count = 0
        
        for i, line in enumerate(lines[:100]):
            if 'buena' in line.lower():
                buena_count += 1
                buena_samples.append({
                    "line_number": i,
                    "content": line[:150]
                })
        
        del content, text, lines
        gc.collect()
        
        return {
            "filename": file.filename,
            "total_lines": len(lines) if 'lines' in locals() else 0,
            "buena_samples": buena_samples,
            "buena_count": buena_count,
            "status": "completed"
        }
        
    except Exception as e:
        return {
            "filename": file.filename if file else "unknown",
            "error": str(e),
            "status": "failed"
        }

@app.post("/test_clean")
async def test_clean(file: UploadFile = File(...)):
    """Probar solo la limpieza del archivo"""
    try:
        content = await file.read()
        text = content.decode('utf-8', errors='ignore')
        
        print(f"DEBUG: Texto original: {len(text)} caracteres")
        
        # Aplicar limpieza
        cleaned = limpiar_log_irclog_avanzado(text)
        lines = cleaned.split('\n')
        
        print(f"DEBUG: Después de limpiar: {len(cleaned)} caracteres, {len(lines)} líneas")
        
        # Buscar líneas con "la buena:" después de limpiar
        buena_lines = []
        for i, line in enumerate(lines):
            if 'la buena:' in line.lower() or 'las buenas:' in line.lower():
                buena_lines.append({
                    "line_number": i,
                    "content": line[:200]
                })
        
        return {
            "filename": file.filename,
            "original_length": len(text),
            "cleaned_length": len(cleaned),
            "total_lines": len(lines),
            "buena_lines_found": len(buena_lines),
            "buena_samples": buena_lines[:5],
            "cleaning_success": len(buena_lines) > 0
        }
        
    except Exception as e:
        return {"error": str(e)}

@app.post("/process_file_direct")
async def process_file_direct(file: UploadFile = File(...)):
    """Procesa archivo directamente"""
    try:
        print(f"DEBUG: Iniciando process_file_direct para {file.filename}")
        
        content = await file.read()
        text_content = content.decode('utf-8', errors='ignore')
        print(f"DEBUG: Archivo {file.filename}, {len(text_content)} caracteres")
        
        # Limpiar
        cleaned = limpiar_log_irclog_avanzado(text_content)
        lines = cleaned.split('\n')
        print(f"DEBUG: Después de limpiar: {len(lines)} líneas")
        
        # Buscar líneas con respuestas
        buena_count = 0
        for line in lines:
            if 'la buena:' in line.lower() or 'las buenas:' in line.lower():
                buena_count += 1
        
        print(f"DEBUG: Encontradas {buena_count} líneas con respuestas")
        
        # Procesar bloques si hay preguntas
        if buena_count > 0:
            result = build_blocks_safe(cleaned)
            result["filename"] = file.filename
            result["cleaning_info"] = {
                "original_length": len(text_content),
                "cleaned_length": len(cleaned),
                "questions_found": buena_count
            }
        else:
            result = {
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
        
        del content, text_content, cleaned, lines
        gc.collect()
        
        return result
        
    except Exception as e:
        print(f"ERROR en process_file_direct: {str(e)}")
        return {
            "filename": file.filename if file else "unknown",
            "total_questions": 0,
            "total_lines": 0,
            "blocks": [],
            "error": str(e)
        }

@app.post("/clean_log")
async def clean_log(request: Request):
    """Action 1: Limpia códigos IRC del texto"""
    try:
        body = await request.body()
        text_content = body.decode('utf-8', errors='ignore')
        
        if not text_content.strip():
            return {
                "status": "error",
                "error": "Contenido vacío",
                "cleaned_text": "",
                "question_lines_found": 0
            }
        
        cleaned = limpiar_log_irclog_avanzado(text_content)
        lines = cleaned.split('\n')
        buena_lines = [i for i, line in enumerate(lines) if 'la buena:' in line.lower() or 'las buenas:' in line.lower()]
        
        return {
            "status": "cleaned",
            "original_length": len(text_content),
            "cleaned_length": len(cleaned), 
            "total_lines": len(lines),
            "question_lines_found": len(buena_lines),
            "cleaned_text": cleaned,
            "preview_first_200": cleaned[:200],
            "preview_last_200": cleaned[-200:] if len(cleaned) > 200 else ""
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "cleaned_text": "",
            "question_lines_found": 0
        }

@app.post("/process_text_plain")
async def process_text_plain(request: Request):
    """Action 2: Procesa texto limpio"""
    try:
        body = await request.body()
        text_content = body.decode('utf-8', errors='ignore')
        
        if not text_content.strip():
            raise HTTPException(400, "Contenido vacío")
        
        result = build_blocks_safe(text_content)
        result["filename"] = "log_procesado.txt"
        
        return result
    
    except Exception as e:
        raise HTTPException(500, f"Error procesando texto: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API v2.1", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/test_sample")
async def test_sample():
    """Test con muestra del log real"""
    sample = """23:02:07'921 <Saga_Noren> 2,0 La buena: 0,4 AMENA2,0 Mandada por: ADRASTEA
23:02:35'697 <Saga_Noren> 2,0 Las buenas: 0,4 VIRTUAL PRIVATE NETWORK, RED PRIVADA VIRTUAL2,0 Mandada por: CORT"""
    
    cleaned = limpiar_log_irclog_avanzado(sample)
    lines = cleaned.split('\n')
    questions = detect_question_indices_simple(lines)
    
    return {
        "original_sample": sample,
        "cleaned_sample": cleaned,
        "detected_questions": questions,
        "cleaning_worked": len(questions) > 0
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
