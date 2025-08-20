from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
import json
from typing import List, Dict, Any
import uvicorn
import gc
import codecs

app = FastAPI(title="Trivial IRC Log Processor", version="3.0.0")

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
        'color': re.compile(r'\x03\d{0,2}(?:,\d{1,2})?'),
        'bold': re.compile(r'\x02'),
        'italic': re.compile(r'\x1D'),
        'underline': re.compile(r'\x1F'),
        'reset': re.compile(r'\x0F'),
        'delete': re.compile(r'\x7F'),
        'color_coords': re.compile(r'\b\d{1,2},\d{1,2}\b'),
        'controls': re.compile(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]'),
        'spaces': re.compile(r'\s{2,}'),
    }
    
    # PASO 3: Aplicar limpieza línea por línea
    lines = text.split('\n')
    cleaned_lines = []
    
    for line in lines:
        cleaned = line
        for pattern in patterns.values():
            cleaned = pattern.sub(' ', cleaned)
        cleaned = re.sub(r'\s+', ' ', cleaned.strip())
        cleaned_lines.append(cleaned)
    
    return '\n'.join(cleaned_lines)

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
            answer_clean = re.sub(r'\d+,\d+', '', answer_text)
            answer_clean = re.sub(r'\s+', ' ', answer_clean).strip()
            
            if answer_clean:
                # Buscar contexto anterior (pregunta)
                question_context = ""
                for j in range(max(0, i-10), i):
                    prev_line = lines[j].lower()
                    if any(word in prev_line for word in ['pregunta', 'question', '¿', '?']):
                        question_context = lines[j].strip()
                        break
                
                # Buscar quién mandó la pregunta
                author = ""
                mandada_match = re.search(r'mandada por[:\s]+(\w+)', line_lower)
                if mandada_match:
                    author = mandada_match.group(1).upper()
                
                questions.append({
                    'number': len(questions) + 1,
                    'line_index': i,
                    'answer': answer_clean,
                    'question_context': question_context,
                    'author': author,
                    'raw_line': line
                })
    
    return questions

def find_participants(lines: List[str]) -> List[str]:
    """Encuentra los participantes del juego"""
    participants = set()
    
    for line in lines:
        # Buscar nicks después de timestamps
        match = re.match(r'\d+:\d+:\d+.*?<([^>]+)>', line)
        if match:
            nick = match.group(1)
            if nick not in ['Saga_Noren', 'Bot', 'Server']:  # Excluir bots/servidor
                participants.add(nick)
        
        # Buscar en "mandada por"
        mandada_match = re.search(r'mandada por[:\s]+(\w+)', line.lower())
        if mandada_match:
            participants.add(mandada_match.group(1).upper())
    
    return sorted(list(participants))

def build_narrative_blocks(questions: List[Dict], participants: List[str], total_lines: int) -> Dict[str, Any]:
    """Construye bloques narrativos con toda la información"""
    
    if not questions:
        return {
            "status": "no_questions",
            "total_questions": 0,
            "total_lines": total_lines,
            "participants": participants,
            "blocks": [],
            "message": "No se encontraron preguntas en el log"
        }
    
    # Dividir en bloques de máximo 8 preguntas
    total_questions = len(questions)
    block_size = min(8, max(1, total_questions // 4))  # Entre 1 y 8 preguntas por bloque
    
    blocks = []
    for i in range(0, total_questions, block_size):
        block_questions = questions[i:i + block_size]
        
        block = {
            "block_number": len(blocks) + 1,
            "question_range": [block_questions[0]['number'], block_questions[-1]['number']],
            "questions": []
        }
        
        for q in block_questions:
            block["questions"].append({
                "number": q['number'],
                "answer": q['answer'],
                "author": q['author'],
                "context": q['question_context'][:200] if q['question_context'] else "",
                "line_index": q['line_index']
            })
        
        blocks.append(block)
    
    return {
        "status": "success",
        "total_questions": total_questions,
        "total_lines": total_lines,
        "participants": participants,
        "blocks": blocks,
        "summary": {
            "game_info": f"Partida con {total_questions} preguntas y {len(participants)} participantes",
            "blocks_created": len(blocks),
            "questions_per_block": f"~{block_size} preguntas por bloque"
        }
    }

@app.post("/process_direct")
async def process_direct(request: Request):
    """Endpoint único que procesa todo el log de una vez"""
    try:
        body = await request.body()
        raw_text = body.decode('utf-8', errors='ignore')
        
        if not raw_text.strip():
            return {
                "status": "error",
                "error": "Contenido vacío"
            }
        
        # PASO 1: Limpiar códigos IRC
        cleaned_text = limpiar_log_irclog_avanzado(raw_text)
        lines = cleaned_text.split('\n')
        
        # PASO 2: Detectar preguntas
        questions = detect_questions_advanced(lines)
        
        # PASO 3: Encontrar participantes
        participants = find_participants(lines)
        
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
        return {
            "status": "error",
            "error": str(e),
            "debug_info": f"Error procesando log: {str(e)}"
        }

# Endpoints de utilidad
@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API v3.0 - Versión Simplificada", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "3.0.0"}

@app.get("/test_sample")
async def test_sample():
    """Test con muestra del log real"""
    sample = """23:02:07'921 <Saga_Noren> 2,0 La buena: 0,4 AMENA2,0 Mandada por: ADRASTEA
23:02:35'697 <Saga_Noren> 2,0 Las buenas: 0,4 VIRTUAL PRIVATE NETWORK, RED PRIVADA VIRTUAL2,0 Mandada por: CORT
23:03:15'234 <Player1> alguna pista de esta?
23:03:45'567 <Saga_Noren> 2,0 La buena: 0,4 MADRID2,0 Mandada por: PLAYER123"""
    
    # Procesarlo con el nuevo endpoint
    cleaned = limpiar_log_irclog_avanzado(sample)
    lines = cleaned.split('\n')
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
