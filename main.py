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

def strip_for_detection(text: str) -> str:
    """Limpia códigos IRC solo para detección, NO para retorno"""
    # Remover códigos de color y control IRC más agresivamente
    clean = re.sub(r'[\x02\x03\x0f\x16\x1d\x1f]', '', text)
    clean = re.sub(r'\x03\d{1,2}(,\d{1,2})?', '', clean)
    # Remover patrones de color específicos como "2,0" "0,4" etc.
    clean = re.sub(r'\d+,\d+', ' ', clean)
    # Limpiar espacios múltiples
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def detect_question_indices(lines: List[str]) -> List[Dict]:
    """Detecta índices de preguntas por líneas con 'La(s) buena(s)'"""
    questions = []
    
    for i, line in enumerate(lines):
        # Debugging específico
        if 'La buena:' in line or 'Las buenas:' in line:
            print(f"DEBUG: Línea {i}: {repr(line[:100])}")
        
        clean_line = strip_for_detection(line)
        
        # Debug de línea limpia
        if 'La buena' in clean_line:
            print(f"DEBUG: Línea limpia {i}: {repr(clean_line[:100])}")
        
        # Regex más flexible
        patterns = [
            r'Las?\s+buena?s?\s*[:\-]\s*(.+?)\s*Mandada por:',
            r'La\s+buena\s*:\s*(.+?)\s*Mandada por:',
            r'Las\s+buenas\s*:\s*(.+?)\s*Mandada por:'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, clean_line, re.IGNORECASE)
            if match:
                answer = match.group(1).strip()
                # Limpiar respuesta
                answer = re.sub(r'\s+', ' ', answer).strip()
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
            "blocks": []
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
                "text_clean": strip_for_detection(question_text)
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
            "text_clean": strip_for_detection(block_text)
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
        
        # Intentar diferentes codificaciones
        try:
            text_content = body.decode('utf-8')
        except UnicodeDecodeError:
            try:
                text_content = body.decode('latin-1')
            except:
                text_content = body.decode('utf-8', errors='ignore')
        
        if not text_content.strip():
            raise HTTPException(400, "Contenido vacío")
        
        # Debug: mostrar primeras líneas para verificar contenido
        lines_preview = text_content.split('\n')[:5]
        print(f"DEBUG: Recibidas {len(text_content.split(chr(10)))} líneas")
        print(f"DEBUG: Primeras líneas: {lines_preview}")
            
        result = build_blocks(text_content)
        result["filename"] = "log_desde_texto.txt"
        
        # Debug: mostrar resultado
        print(f"DEBUG: Detectadas {result['total_questions']} preguntas")
        
        return result
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        raise HTTPException(500, f"Error procesando texto: {str(e)}")

@app.post("/debug_log")
async def debug_log(log_content: str):
    """Debug endpoint para probar detección de preguntas"""
    try:
        # Procesar el contenido
        lines = log_content.split('\n')
        
        # Buscar líneas con "La buena" o "Las buenas"
        buena_lines = []
        for i, line in enumerate(lines):
            if 'La buena:' in line or 'Las buenas:' in line:
                buena_lines.append({
                    "line_number": i,
                    "content": line,
                    "clean_content": strip_for_detection(line)
                })
        
        # Intentar detectar preguntas
        questions = detect_question_indices(lines)
        
        return {
            "total_lines": len(lines),
            "lines_with_buena": buena_lines,
            "detected_questions": len(questions),
            "questions": questions,
            "sample_lines": lines[:5]
        }
        
    except Exception as e:
        return {"error": str(e), "details": "Error procesando el log"}

@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)


