from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import re, zipfile, io

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

CTRL_CODES = re.compile(r'[\x00-\x1f\x7f]')
IRC_COLOR = re.compile(r'\x03(\d{1,2}(,\d{1,2})?)?')
BOLD_ITALIC_ETC = re.compile(r'[\x02\x1F\x16\x0F]')
BUENA_PAT = re.compile(r'La[s]?\s+buena[s]?\s*[:\-]\s*(.*)', re.IGNORECASE)

def strip_irc(s:str)->str:
    s = IRC_COLOR.sub('', s)
    s = BOLD_ITALIC_ETC.sub('', s)
    s = CTRL_CODES.sub('', s)
    return s

def load_text_from_upload(upload: UploadFile) -> str:
    data = upload.file.read()
    name = upload.filename.lower()
    if name.endswith(".txt"):
        return data.decode("utf-8", errors="ignore")
    if name.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for zi in z.infolist():
                if zi.filename.lower().endswith(".txt"):
                    return z.read(zi).decode("utf-8", errors="ignore")
        raise HTTPException(400, "ZIP sin TXT válido dentro.")
    raise HTTPException(400, "Sube .txt o .zip")

def build_blocks(raw: str):
    lines = [strip_irc(l) for l in raw.splitlines()]
    buena_idxs, answers = [], []
    for i, l in enumerate(lines):
        m = BUENA_PAT.search(l)
        if m:
            ans = re.split(r'\bMandada\s+por\b\s*:\s*', m.group(1), flags=re.IGNORECASE)[0].strip(" -—:·\t")
            buena_idxs.append(i)
            answers.append(ans)
    N = len(buena_idxs)
    if N == 0:
        return {"total_questions": 0, "blocks": []}

    base, rest = divmod(N, 5)
    sizes = [(base+1 if i < rest else base) for i in range(5)]
    sizes = [s for s in sizes if s > 0]

    blocks, idx, qnum, prev_end = [], 0, 1, -1
    for b, size in enumerate(sizes, start=1):
        block_qs = []
        for _ in range(size):
            start_idx = prev_end + 1
            end_idx = buena_idxs[idx]
            snippet = "\n".join(lines[start_idx:end_idx+1]).strip()
            block_qs.append({"idx": qnum, "answer": answers[idx], "text": snippet})
            prev_end = end_idx
            idx += 1
            qnum += 1
        blocks.append({
            "block": b,
            "q_index_range": [block_qs[0]["idx"], block_qs[-1]["idx"]],
            "questions": block_qs
        })
    return {"total_questions": N, "blocks": blocks}

@app.post("/process")
from fastapi import Body

@app.post("/process_text")
async def process_text(text: str = Body(..., embed=True)):
    # Reutilizamos build_blocks pero con texto directo
    data = build_blocks(text)
    return JSONResponse(data)
