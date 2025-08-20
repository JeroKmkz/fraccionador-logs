# main.py v4.0 - Solo funciones auxiliares
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import re
import json
import uvicorn

app = FastAPI(title="Trivial IRC Helper", version="4.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://chat.openai.com", "https://chatgpt.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/get_patterns")
async def get_patterns():
    """Devuelve patrones de limpieza IRC para que el GPT los use"""
    return {
        "irc_patterns": {
            "color_codes": r"\\x03\\d{0,2}(?:,\\d{1,2})?",
            "bold": r"\\x02",
            "italic": r"\\x1D", 
            "underline": r"\\x1F",
            "reset": r"\\x0F",
            "controls": r"[\\x00-\\x08\\x0B-\\x0C\\x0E-\\x1F]",
            "color_coords": r"\\b\\d{1,2},\\d{1,2}\\b"
        },
        "question_patterns": {
            "answer_line": r"(la buena:|las buenas:)(.+?)(?:mandada por|$)",
            "author": r"mandada por[:\\s]+([^\\s,]+)",
            "question_line": r"pregunta[:\\s]+(\\d+)",
            "timestamp": r"\\d+:\\d+:\\d+"
        },
        "participant_patterns": {
            "nick": r"\\d+:\\d+:\\d+.*?<([^>]+)>",
            "exclude_bots": ["Saga_Noren", "VegaSicilia", "Bot", "Server", "GleviBot"]
        }
    }

@app.post("/validate_sample")
async def validate_sample(request: Request):
    """Valida que un fragmento pequeño se procese correctamente"""
    try:
        body = await request.body()
        sample = body.decode('utf-8', errors='ignore')
        
        # Buscar respuestas en el sample
        answers = []
        lines = sample.split('\\n')
        
        for line in lines:
            if 'la buena:' in line.lower() or 'las buenas:' in line.lower():
                # Extraer respuesta simple
                if 'la buena:' in line.lower():
                    start = line.lower().find('la buena:') + 9
                else:
                    start = line.lower().find('las buenas:') + 11
                    
                end = line.lower().find('mandada por', start)
                if end == -1:
                    answer = line[start:].strip()
                else:
                    answer = line[start:end].strip()
                    
                # Limpiar
                answer_clean = re.sub(r'\\d+,\\d+', '', answer)
                answer_clean = re.sub(r'\\s+', ' ', answer_clean).strip()
                
                if answer_clean:
                    answers.append(answer_clean)
        
        return {
            "status": "validated",
            "sample_length": len(sample),
            "answers_found": len(answers),
            "answers": answers[:3],  # Solo las primeras 3
            "processing_works": len(answers) > 0
        }
        
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get("/")
async def root():
    return {"message": "Trivial IRC Helper v4.0 - GPT Autónomo", "status": "running"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
