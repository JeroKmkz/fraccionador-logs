from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import re
import json
from typing import List, Dict, Any
import uvicorn
import codecs

app = FastAPI(title="Trivial IRC Log Processor", version="3.2.0")

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
    try:
        text = codecs.decode(text, 'unicode_escape')
    except:
        pass
    
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
            if 'la buena:' in line_lower:
                start_pos = line_lower.find('la buena:') + 9
            else:
                start_pos = line_lower.find('las buenas:') + 11
            
            end_pos = line_lower.find('mandada por', start_pos)
            if end_pos == -1:
                answer_text = line[start_pos:].strip()
            else:
                answer_text = line[start_pos:end_pos].strip()
            
            answer_clean = re.sub(r'\\d+,\\d+', '', answer_text)
            answer_clean = re.sub(r'\\s+', ' ', answer_clean).strip()
            
            if answer_clean:
                question_context = ""
                for j in range(max(0, i-15), i):
                    prev_line = lines[j]
                    prev_line_lower = prev_line.lower()
                    
                    if any(word in prev_line_lower for word in ['pregunta:', '¿', '?']) and len(prev_line.strip()) > 20:
                        question_context = limpiar_log_irclog_avanzado(prev_line.strip())
                        break
                
                author = ""
                mandada_match = re.search(r'mandada por[:\\s]+([^\\s,]+)', line_lower)
                if mandada_match:
                    author = mandada_match.group(1).upper()
                
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
        match = re.match(r'\\d+:\\d+:\\d+.*?<([^>]+)>', line)
        if match:
            nick = match.group(1)
            if nick not in ['Saga_Noren', 'VegaSicilia', 'Bot', 'Server', 'GleviBot']:
                participants.add(nick)
        
        mandada_match = re.search(r'mandada por[:\\s]+([^\\s,]+)', line.lower())
        if mandada_match:
            author = mandada_match.group(1).upper()
            if author not in ['FIREBALL', 'CASTRO', 'BOT']:
                participants.add(author)
    
    return sorted(list(participants))

@app.post("/process_direct")
async def process_direct(request: Request):
    """Endpoint único que procesa log completo con límite de 12 preguntas por respuesta"""
    try:
        body = await request.body()
        raw_text = body.decode('utf-8', errors='ignore')
        
        print(f"DEBUG: Recibido texto de {len(raw_text)} caracteres")
        
        if not raw_text.strip():
            return {"status": "error", "error": "Contenido vacío"}
        
        # Limpiar códigos IRC
        cleaned_text = limpiar_log_irclog_avanzado(raw_text)
        lines = cleaned_text.split('\\n')
        
        # Detectar preguntas
        all_questions = detect_questions_advanced(lines)
        participants = find_participants(lines)
        
        print(f"DEBUG: Total preguntas detectadas: {len(all_questions)}")
        
        # Limitar a las primeras 12 preguntas
        limited_questions = all_questions[:12]
        remaining_questions = len(all_questions) - 12
        
        # Crear bloques (4 preguntas por bloque)
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
        
        return {
            "status": "success",
            "total_questions": len(all_questions),
            "total_lines": len(lines),
            "participants": participants[:10],
            "blocks": blocks,
            "summary": {
                "game_info": f"Partida con {len(all_questions)} preguntas y {len(participants)} participantes",
                "blocks_created": len(blocks),
                "showing_first": len(limited_questions),
                "remaining_questions": remaining_questions if remaining_questions > 0 else 0
            },
            "processing_info": {
                "original_length": len(raw_text),
                "cleaned_length": len(cleaned_text),
                "lines_processed": len(lines)
            }
        }
        
    except Exception as e:
        print(f"ERROR: {str(e)}")
        return {"status": "error", "error": str(e)}

@app.post("/continue_from")
async def continue_from(request: Request):
    """Continúa procesando desde una pregunta específica"""
    try:
        body = await request.body()
        
        # Limpiar caracteres problemáticos antes de parsear JSON
        body_text = body.decode('utf-8', errors='ignore')
        body_clean = re.sub(r'[\\x00-\\x1F\\x7F-\\x9F]', ' ', body_text)
        body_clean = re.sub(r'[""''´`]', '"', body_clean)
        
        try:
            data = json.loads(body_clean)
        except json.JSONDecodeError as e:
            print(f"ERROR JSON: {e}")
            return {"status": "error", "error": f"Error parsing JSON: {str(e)}"}
        
        raw_text = data.get('text', '')
        start_question = data.get('start_question', 13)
        
        if not raw_text.strip():
            return {"status": "error", "error": "Contenido vacío"}
        
        print(f"DEBUG: Continuando desde pregunta {start_question}")
        
        # Procesar texto
        cleaned_text = limpiar_log_irclog_avanzado(raw_text)
        lines = cleaned_text.split('\\n')
        all_questions = detect_questions_advanced(lines)
        
        # Filtrar preguntas desde start_question
        questions_subset = [q for q in all_questions if q['number'] >= start_question]
        limited_questions = questions_subset[:12]
        
        print(f"DEBUG: Preguntas en este bloque: {len(limited_questions)}")
        
        # Crear bloques
        blocks = []
        block_size = 4
        
        for i in range(0, len(limited_questions), block_size):
            block_questions = limited_questions[i:i + block_size]
            
            if not block_questions:
                continue
                
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
        print(f"ERROR en continue_from: {str(e)}")
        return {"status": "error", "error": str(e)}

@app.get("/")
async def root():
    return {"message": "Trivial IRC Log Processor API v3.2 - Solo Texto", "status": "running"}

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "3.2.0"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
