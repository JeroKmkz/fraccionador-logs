from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
from typing import List, Dict, Any
import uvicorn
import gc  # Para manejo de memoria

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
    Limpiador avanzado que maneja códigos IRC en formato \uXXXX
    """
    import re
    
    # PRIMERO: Convertir códigos unicode escapados a caracteres reales
    try:
        text = text.encode().decode('unicode_escape')
    except:
        pass
    
    # Patrones de limpieza
    patterns = {
        # Códigos de color (\x03 seguido de dígitos)
        'color': re.compile(r'\x03\d{1,2}(?:,\d{1,2})?'),
        'bold': re.compile(r'\x02'),
        'italic': re.compile(r'\x1D'),
        'underline': re.compile(r'\x1F'),
        'reset': re.compile(r'\x0F'),
        'delete': re.compile(r'\x7F'),
        
        # Códigos de color tipo "2,0" sueltos
        'color_coords': re.compile(r'\b\d{1,2},\d{1,2}\b'),
        
        # Secuencias ANSI
        'ansi': re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])'),
        
        # Múltiples espacios
        'multiple_spaces': re.compile(r'\s{2,}'),
    }
    
    # Aplicar limpieza
    cleaned = text
    for pattern_name, pattern in patterns.items():
        cleaned = pattern.sub('', cleaned)
    
    # Limpiar espacios múltiples y normalizar
    cleaned = re.sub(r'\s+', ' ', cleaned)
    
    return cleaned

def detect_question_indices_simple(lines: List[str]) -> List[Dict]:
    """Detección súper simple de preguntas"""
    questions = []
    
    try:
        for i, line in enumerate(lines):
            # Buscar simplemente "la buena:" o "las buenas:" (case insensitive)
            line_lower = line.lower()
            
            if 'la buena:' in line_lower or 'las buenas:' in line_lower:
                print(f"DEBUG encontrada línea {i}: {line[:100]}")
                
                # Extraer respuesta de forma muy simple
                if 'la buena:' in line_lower:
                    start_pos = line_lower.find('la buena:') + 9
                else:
                    start_pos = line_lower.find('las buenas:') + 11
                
                # Buscar hasta "mandada por" o final
                end_pos = line_lower.find('mandada por', start_pos)
                if end_pos == -1:
                    answer_text = line[start_pos:].strip()
                else:
                    answer_text = line[start_pos:end_pos].strip()
                
                # Limpiar códigos residuales de la respuesta
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
            # Calcular preguntas en este bloque
            block_size = base_size + (1 if block_num < remainder else 0)
            q_end = q_start + block_size
            
            # Línea final del bloque
            end_line = questions[q_end - 1]['line_index']
            
            # Construir preguntas del bloque
            block_questions = []
            for q_idx in range(q_start, q_end):
                question = questions[q_idx]
                
                # Rango de líneas para esta pregunta
                q_start_line = questions[q_idx - 1]['line_index'] + 1 if q_idx > 0 else start_line
                q_end_line = question['line_index']
                
                # Texto de la pregunta
                question_lines = lines[q_start_line:q_end_line + 1]
                question_text = '\n'.join(question_lines)
                
                block_questions.append({
                    "idx": question['idx'],
                    "answer": question['answer'],
                    "line_range": [q_start_line, q_end_line],
                    "text_raw": question_text[:1000],  # Limitar tamaño para evitar memoria
                    "text_clean": question_text[:1000]  # Simplificado
                })
            
            # Texto del bloque completo
            block_lines = lines[start_line:end_line + 1]
            block_text = '\n'.join(block_lines)
            
            blocks.append({
                "block": block_num + 1,
                "q_index_range": [questions[q_start]['idx'], questions[q_end - 1]['idx']],
                "line_range": [start_line, end_line],
                "questions": block_questions,
                "text_raw": block_text[:2000] if len(block_text) <= 2000 else block_text[:2000] + "...[truncado]",
                "text_clean": ""  # Vacío para ahorrar memoria
            })
            
            # Siguiente bloque
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
        print(f"DEBUG: Leídos {len(content)} bytes")
        
        text = content.decode('utf-8', errors='ignore')
        lines = text.split('\n')
        print(f"DEBUG: {len(lines)} líneas totales")
        
        # Buscar líneas con "buena" en las primeras 100 líneas
        buena_samples = []
        buena_count = 0
        
        for i, line in enumerate(lines[:100]):  # Solo primeras 100 líneas
            if 'buena' in line.lower():
                buena_count += 1
                buena_samples.append({
                    "line_number": i,
                    "content": line[:150]  # Solo primeros 150 chars
                })
        
        # Liberar memoria
        del content, text, lines
        gc.collect()
        
        print(f"DEBUG: Encontradas {buena_count} líneas con 'buena'")
        
        return {
            "filename": file.filename,
            "total_lines": len(lines) if 'lines' in locals() else 0,
            "buena_samples": buena_samples,
            "buena_count": buena_count,
            "status": "completed"
        }
        
    except Exception as e:
        print(f"ERROR en count_lines: {e}")
        return {
            "filename": file.filename if file else "unknown",
            "error": str(e),
            "status": "failed"
        }

@app.post("/process_file_direct")
async def process_file_direct(file: UploadFile = File(...)):
    """Procesa archivo directamente sin pasar por ChatGPT"""
    try:
        print(f"DEBUG: Iniciando process_file_direct para {file.filename}")
        
        # Leer contenido
        content = await file.read()
        text_content = content.decode('utf-8', errors='ignore')
        print(f"DEBUG: Archivo {file.filename}, {len(text_content)} caracteres")
        
        # PASO 1: Limpiar
        cleaned = limpiar_log_irclog_avanzado(text_content)
        lines = cleaned.split('\n')
        print(f"DEBUG: Después de limpiar: {len(lines)} líneas")
        
        # PASO 2: Buscar líneas con "buena" manualmente
        buena_count = 0
        for line in lines:
            if 'la buena:' in line.lower() or 'las buenas:' in line.lower():
                buena_count += 1
        
        print(f"DEBUG: Encontradas {buena_count} líneas con respuestas")
        
        # PASO 3: Procesar bloques solo si hay preguntas
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
        
        # Liberar memoria
        del content, text_content, cleaned, lines
        gc.collect()
        
        print(f"DEBUG: Proceso completado")
        return result
        
    except Exception as e:
        print(f"ERROR CRÍTICO en process_file_direct: {str(e)}")
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
    
    # Limpiar
    cleaned = limpiar_log_irclog_avanzado(sample)
    
    # Detectar preguntas
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

