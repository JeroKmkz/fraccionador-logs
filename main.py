from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uuid
from datetime import datetime, timedelta
import re

app = FastAPI(title="Trivial Chunker API", version="11.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sesiones en memoria
sessions_storage = {}

class SessionData:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.created_at = datetime.now()
        self.last_access = datetime.now()
        self.full_text = ""
        self.question_blocks = []
        self.total_questions = 0
        self.metadata = {}
        self.processed = False

def clean_irc_codes(text: str) -> str:
    text = re.sub(r'\x03\d{0,2}(?:,\d{1,2})?', '', text)
    text = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', text)
    text = re.sub(r'(?:^|\s)\d+,\d+\s+', ' ', text)
    return text.strip()

def extract_and_chunk_questions(text: str, questions_per_block: int = 5):
    # (tu lógica actual de detección de preguntas)
    return []

def cleanup_old_sessions():
    cutoff = datetime.now() - timedelta(hours=3)
    expired = [sid for sid, s in sessions_storage.items() if s.created_at < cutoff]
    for sid in expired:
        del sessions_storage[sid]

@app.post("/upload_log_file")
async def upload_log_file(file: UploadFile = File(...)):
    """
    Nuevo endpoint: permite subir directamente el log como archivo
    """
    try:
        content_bytes = await file.read()
        text = content_bytes.decode("utf-8", errors="ignore")
        text = clean_irc_codes(text)

        session_id = str(uuid.uuid4())[:8]
        session = SessionData(session_id)
        session.full_text = text

        session.question_blocks = extract_and_chunk_questions(text, 5)
        session.total_questions = sum(len(block) for block in session.question_blocks)
        session.processed = True

        session.metadata = {
            "filename": file.filename,
            "total_lines": len(text.split("\n")),
            "total_blocks": len(session.question_blocks),
            "questions_per_block": 5,
            "size_bytes": len(content_bytes),
            "equipos": []
        }

        if "FOGUETES" in text[:3000]:
            session.metadata["equipos"].append("FOGUETES")
        if "LIDERES" in text[:3000] or "LÍDERES" in text[:3000]:
            session.metadata["equipos"].append("LIDERES")

        sessions_storage[session_id] = session
        cleanup_old_sessions()

        return JSONResponse({
            "session_id": session_id,
            "status": "success",
            "total_questions": session.total_questions,
            "total_blocks": len(session.question_blocks),
            "questions_per_block": 5,
            "equipos": session.metadata["equipos"],
            "message": f"Archivo procesado en {len(session.question_blocks)} bloques de 5 preguntas",
            "instructions": f"Usa /get_block/{session_id}/1 para obtener el primer bloque"
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error procesando archivo: {str(e)}")

