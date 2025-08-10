from fastapi import Request
from fastapi import FastAPI, UploadFile, File, HTTPException, Body
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import re, zipfile, io

# -----------------------------
# App + CORS
# -----------------------------
app = FastAPI(title="Trivial Chunker API", version="1.2.0")

# CORS abierto (si quieres, luego limita dominios en allow_origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -----------------------------
# Patrones y utilidades
# -----------------------------
CTRL_CODES = re.compile(r'[\x00-\x1f\x7f]')
IRC_COLOR = re.compile(r'\x03(\d{1,2}(,\d{1,2})?)?')
BOLD_ITALIC_ETC = re.compile(r'[\x02\x1F\x16\x0F]')
# Captura "La buena:" / "Las buenas:" con posibles espacios/guiones y se queda con lo que hay hasta "Mandada por:"
BUENA_PAT = re.compile(r'La[s]?\s+buena[s]?\s*[:\-]\s*(.*)', re.IGNORECASE)

def strip_irc(s: str) -> str:
    """Quita códigos de formato IRC y control."""
    if not isinstance(s, str):
        return ""
    s = IRC_COLOR.sub("", s)
    s = BOLD_ITALIC_ETC.sub("", s)
    s = CTRL_CODES.sub("", s)
    return s

def load_text_from_upload(upload: UploadFile) -> str:
    """Lee .txt directamente o extrae el primer .txt válido dentro de un .zip."""
    data = upload.file.read()
    name = (upload.filename or "").lower()
    if name.endswith(".txt"):
        # intenta utf-8 y tolera caracteres raros
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".zip"):
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                for zi in z.infolist():
                    if zi.filename.lower().endswith(".txt"):
                        return z.read(zi).decode("utf-8", errors="ignore")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="ZIP inválido.")
        raise HTTPException(status_code=400, detail="ZIP sin ningún .txt dentro.")
    raise HTTPException(status_code=400, detail="Sube un .txt o un .zip con un .txt dentro.")

def build_blocks(raw: str):
    """
    Limpia el texto, detecta finales de pregunta por 'La buena/Las buenas',
    y divide en hasta 5 bloques equilibrados (o menos si hay menos preguntas).
    Devuelve { total_questions, blocks[] }.
    """
    lines = [strip_irc(l) for l in (raw.splitlines() if isinstance(raw, str) else [])]
    buena_idxs, answers = [], []

    for i, l in enumerate(lines):
        m = BUENA_PAT.search(l)
        if m:
            # Cortar cualquier 'Mandada por:' que venga detrás
            part = re.split(r'\bMandada\s+por\b\s*:\s*', m.group(1), flags=re.IGNORECASE)[0]
            ans = part.strip(" -—:·\t")
            buena_idxs.append(i)
            answers.append(ans)

    N = len(buena_idxs)
    if N == 0:
        return {"total_questions": 0, "blocks": []}

    # repartir N en 5 bloques lo más equilibrados posible
    base, rest = divmod(N, 5)
    sizes = [(base + 1 if i < rest else base) for i in range(5)]
    sizes = [s for s in sizes if s > 0]  # si hay menos de 5 bloques reales

    blocks, idx, qnum, prev_end = [], 0, 1, -1
    for b, size in enumerate(sizes, start=1):
        block_qs = []
        for _ in range(size):
            start_idx = prev_end + 1
            end_idx = buena_idxs[idx]
            snippet = "\n".join(lines[start_idx:end_idx + 1]).strip()
            block_qs.append({
                "idx": qnum,             # número de pregunta secuencial
                "answer": answers[idx],  # texto de la(s) respuesta(s) de esa pregunta
                "text": snippet          # trozo de log hasta el "La buena/Las buenas"
            })
            prev_end = end_idx
            idx += 1
            qnum += 1
        blocks.append({
            "block": b,
            "q_index_range": [block_qs[0]["idx"], block_qs[-1]["idx"]],
            "questions": block_qs
        })

    return {"total_questions": N, "blocks": blocks}

# -----------------------------
# Endpoints
# -----------------------------
@app.get("/")
def root():
    return {"ok": True, "message": "Trivial Chunker API ready. Use /process or /process_text."}

@app.post("/process")
async def process(file: UploadFile = File(...)):
    """
    Sube un .txt o un .zip con .txt y devuelve el troceo en JSON.
    """
    raw = load_text_from_upload(file)
    data = build_blocks(raw)
    return JSONResponse(data)

@app.post("/process_text")
async def process_text(text: str = Body(..., embed=True)):
    """
    Envía el contenido del log como texto (JSON) y devuelve el troceo.
    """
    data = build_blocks(text)
    return JSONResponse(data)

@app.post("/process_text_plain")
async def process_text_plain(request: Request):
    """
    Recibe el contenido del log como texto plano (text/plain) y devuelve el troceo.
    Evita problemas de JSON con caracteres de control.
    """
    raw_bytes = await request.body()
    try:
        text = raw_bytes.decode("utf-8", errors="ignore")
    except Exception:
        text = str(raw_bytes, "utf-8", errors="ignore")
    data = build_blocks(text)
    return JSONResponse(data)
