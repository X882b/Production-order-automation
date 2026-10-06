import os

from dotenv import load_dotenv
load_dotenv(override=True)

from fastapi import FastAPI, Depends, Header, HTTPException
from sqlalchemy import text

from server.db import engine
from server.routes_lookup import router as lookup_router
from server.routes_documents_finalize import router as finalize_router
from server.routes_doc_colors import router as doc_colors_router
from server.routes_series import router as series_router

API_KEY = os.getenv("API_KEY")

app = FastAPI(title="YU LABEL DMS")

def require_api_key(x_api_key: str | None = Header(default=None)):
    if not API_KEY:
        raise HTTPException(status_code=500, detail="Server missing API_KEY")
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="bad api key")

# ✅ protect all router endpoints too
app.include_router(lookup_router, dependencies=[Depends(require_api_key)])
app.include_router(finalize_router, dependencies=[Depends(require_api_key)])
app.include_router(doc_colors_router, dependencies=[Depends(require_api_key)])
app.include_router(series_router, dependencies=[Depends(require_api_key)])

@app.get("/ping", dependencies=[Depends(require_api_key)])
def ping():
    return {"ok": True, "msg": "pong"}

@app.post("/documents/reserve-number", dependencies=[Depends(require_api_key)])
def reserve_number(username: str = "watcher"):
    with engine.begin() as cx:
        num = cx.execute(text("SELECT nextval('doc_number_seq')")).scalar_one()
        cx.execute(text("""
            INSERT INTO documents (doc_number, title, status, created_by)
            VALUES (:n, '', 'draft', :u)
        """), {"n": num, "u": username})
    return {"doc_number": num}


