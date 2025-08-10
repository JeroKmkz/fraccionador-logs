from fastapi import FastAPI, UploadFile, File, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
from typing import List, Dict, Any
import uvicorn

app = FastAPI(title="Trivial IRC Log Processor", version="1.0.0")

# CORS para ChatGPT
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def limpiar_log_irclog(text: str) -> str:
    """
    Limpia códigos IRC del texto completo
    Basado en el limpiador proporcionado
    """
    # Patrones IRC molestos (tanto formato \x como \u0003)
    bold_pattern = re.compile(r"[\x02\u0002]")                    # Negrita
    color_pattern = re.compile(r"[\x03\u0003]\d{0,2}(,\d{0,2})?")  # Colores IRC
    reset_pattern = re.compile(r"[\x0f\u000f]")                   # Reset de formato
    delete_pattern = re.compile(r"[\x7f\u007f]")                  # Delete
    other_controls = re.compile(r"[\x16\x1d\x1f\u0016\u001d\u001f]")  # Otros controles
    coordinates_pattern = re.compile(r"\b\d{1,2},\d{1,2}\b")      # Coordenadas tipo "12,15"

    # Aplicar limpieza
    text = bold_pattern.sub("", text)
    text = color_pattern.sub("", text)
    text = reset_pattern.sub("", text)
    text = delete_pattern.sub("", text)
    text = other_controls.sub("", text)
    text = coordinates_pattern.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)  # Reduce espacios múltiples
    
    return text

def detect_question_indices(lines: List[str]) -> List[Dict]:
    """Detecta índices de preguntas por líneas con 'La(s) buena(s)'"""
    questions = []
    
    for i, line in enumerate(lines):
        # Limpiar la línea para detección
        clean_line = limpiar_log_irclog(line)
        
        # Debug: mostrar líneas que contengan "buena"
        if 'buena' in clean_line.lower():
            print(f"DEBUG línea {i}: {repr(clean_line[:100])}")
        
        # Patrones múltiples para detectar respuestas
        patterns = [
            r'La\s+buena\s*:\s*(.+?)\s*Mandada\s+por:',
            r'Las\s+buenas\s*:\s*(.+?)\s*Mandada\s+por:',
            r'La\s+buena\s*:\s*(.+?)\s*Mandada\s+por',
            r'Las\s+buenas\s*:\s*(.+?)\s*Mandada\s+por'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, clean_line, re.IGNORECASE)
            if match:
                answer = match.group(1).strip()
                
                # Limpiar respuesta final más agresivamente
                answer = re.sub(r'\d+,\d+', '', answer)  # Remover códigos de color residuales
                answer = re.sub(r'\s+', ' ', answer).strip()  # Normalizar espacios
                
                print(f"DEBUG: Respuesta encontrada: {repr(answer)}")
                questions.append({
                    'idx': len(questions) + 1,
                    'line_index': i,
                    'answer': answer
                })
                break
    
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
                "text_clean": limpiar_log_irclog(question_text)
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
            "text_clean": limpiar_log_irclog(block_text)
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
    """Procesa texto plano directamente desde el body"""
    try:
        # Leer el contenido raw del body
        body = await request.body()
        text_content = body.decode('utf-8', errors='ignore')
        
        if not text_content.strip():
            raise HTTPException(400, "Contenido vacío")
        
        print(f"DEBUG: Recibidas {len(text_content.split(chr(10)))} líneas")
        
        result = build_blocks(text_content)
        result["filename"] = "log_desde_texto.txt"
        
        print(f"DEBUG: Resultado: {result['total_questions']} preguntas")
        
        return result
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(500, f"Error procesando texto: {str(e)}")

@app.post("/process_chatgpt")
async def process_chatgpt(request: Request):
    """Endpoint específico para ChatGPT con manejo robusto de caracteres"""
    try:
        # Leer el contenido raw del body
        body = await request.body()
        
        # Intentar decodificar con máxima tolerancia
        try:
            text_content = body.decode('utf-8')
        except UnicodeDecodeError:
            text_content = body.decode('utf-8', errors='replace')
        
        # Limpiar caracteres problemáticos agresivamente
        text_content = re.sub(r'[\x00-\x1f\x7f-\x9f]', ' ', text_content)  # Remover controles
        text_content = re.sub(r'\\u[0-9a-fA-F]{4}', ' ', text_content)      # Remover secuencias unicode
        text_content = re.sub(r'\s+', ' ', text_content)                    # Normalizar espacios
        
        if not text_content.strip():
            return {
                "filename": "error.txt",
                "total_questions": 0,
                "total_lines": 0,
                "blocks": [],
                "error": "Contenido vacío después de limpieza"
            }
        
        print(f"DEBUG ChatGPT: Procesando {len(text_content)} caracteres")
        
        result = build_blocks(text_content)
        result["filename"] = "log_chatgpt.txt"
        
        print(f"DEBUG ChatGPT: Detectadas {result['total_questions']} preguntas")
        
        return result
    
    except Exception as e:
        print(f"ERROR ChatGPT: {str(e)}")
        return {
            "filename": "error.txt",
            "total_questions": 0,
            "total_lines": 0,
            "blocks": [],
            "error": str(e)
        }

@app.post("/debug_received")
async def debug_received(request: Request):
    """Debug: mostrar exactamente qué recibimos de ChatGPT"""
    try:
        body = await request.body()
        text = body.decode('utf-8', errors='replace')
        
        return {
            "total_bytes": len(body),
            "total_chars": len(text),
            "total_lines": len(text.split('\n')),
            "first_200_chars": text[:200],
            "last_200_chars": text[-200:] if len(text) > 200 else text,
            "contains_saga_noren": "Saga_Noren" in text,
            "contains_buena": "buena" in text.lower(),
            "line_count_breakdown": {
                "total": len(text.split('\n')),
                "non_empty": len([l for l in text.split('\n') if l.strip()]),
                "with_saga": len([l for l in text.split('\n') if 'Saga_Noren' in l])
            }
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/test_sample")
async def test_sample():
    """Test con muestra del log real"""
    sample = """23:02:07'921 <Saga_Noren> 2,0 La buena: 0,4 AMENA2,0 Mandada por: ADRASTEA
23:02:35'697 <Saga_Noren> 2,0 Las buenas: 0,4 VIRTUAL PRIVATE NETWORK, RED PRIVADA VIRTUAL2,0 Mandada por: CORT"""
    
    lines = sample.split('\n')
    questions = detect_question_indices(lines)
    
    return {
        "sample_lines": lines,
        "detected_questions": questions,
        "cleaned_lines": [limpiar_log_irclog(line) for line in lines]
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)



