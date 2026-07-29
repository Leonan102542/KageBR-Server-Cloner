import threading
import requests
import logging
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="KageBR Server Cloner")
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def processar_clonagem(token: str, origem_id: str, destino_id: str):
    headers = {"Authorization": token.strip(), "Content-Type": "application/json"}
    base_url = "https://discord.com"
    res_canais = requests.get(f"{base_url}/guilds/{origem_id}/channels", headers=headers)
    if res_canais.status_code != 200:
        return
    canais = res_canais.json()
    canais_ordenados = sorted(canais, key=lambda c: c.get("type", 0) != 4)
    mapa_categorias = {}
    for canal in canais_ordenados:
        payload = {"name": canal["name"], "type": canal["type"], "position": canal.get("position", 0)}
        if canal.get("parent_id") and canal["parent_id"] in mapa_categorias:
            payload["parent_id"] = mapa_categorias[canal["parent_id"]]
        res_criacao = requests.post(f"{base_url}/guilds/{destino_id}/channels", headers=headers, json=payload)
        if res_criacao.status_code == 201 and canal["type"] == 4:
            mapa_categorias[canal["id"]] = res_criacao.json()["id"]

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "status": None})

@app.post("/clonar", response_class=HTMLResponse)
async def clonar(request: Request, token: str = Form(...), origem: str = Form(...), destino: str = Form(...)):
    thread = threading.Thread(target=processar_clonagem, args=(token, origem, destino))
    thread.start()
    return templates.TemplateResponse("index.html", {"request": request, "status": "Clonagem iniciada! Olhe seu Discord."})
  
