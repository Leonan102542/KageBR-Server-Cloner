import threading
import requests
import logging
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="KageBR Server Cloner")
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Dicionário global para armazenar o status e progresso em tempo real
status_clonagem = {
    "total": 0,
    "criados": 0,
    "status": "Aguardando início...",
    "finalizado": False
}

def processar_clonagem(token: str, origen_id: str, destino_id: str):
    global status_clonagem
    status_clonagem = {"total": 0, "criados": 0, "status": "Conectando ao Discord...", "finalizado": False}

    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json"
    }
    base_url = "https://discord.com"

    # 1. Buscar canais da origem
    res_canais = requests.get(f"{base_url}/guilds/{origen_id}/channels", headers=headers)
    if res_canais.status_code != 200:
        status_clonagem["status"] = f"❌ Erro ao ler origem (Status: {res_canais.status_code})"
        status_clonagem["finalizado"] = True
        return

    canais = res_canais.json()
    status_clonagem["total"] = len(canais)
    status_clonagem["status"] = "Estrutura mapeada! Iniciando criação..."

    canais_ordenados = sorted(canais, key=lambda c: c.get("type", 0) != 4)
    mapa_categorias = {}

    # 2. Replicar canais no destino
    for canal in canais_ordenados:
        payload = {
            "name": canal["name"],
            "type": canal["type"],
            "position": canal.get("position", 0)
        }

        if canal.get("parent_id") and canal["parent_id"] in mapa_categorias:
            payload["parent_id"] = mapa_categorias[canal["parent_id"]]

        res_criacao = requests.post(f"{base_url}/guilds/{destino_id}/channels", headers=headers, json=payload)
        
        if res_criacao.status_code == 201:
            novo_canal = res_criacao.json()
            if canal["type"] == 4:
                mapa_categorias[canal["id"]] = novo_canal["id"]
        
        # Atualiza os contadores em tempo real para o celular ler
        status_clonagem["criados"] += 1
        status_clonagem["status"] = f"Criando: {canal['name']}"

    status_clonagem["status"] = "🎉 Clonagem concluída com sucesso!"
    status_clonagem["finalizado"] = True

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/clonar")
async def clonar(token: str = Form(...), origem: str = Form(...), destino: str = Form(...)):
    # Dispara a clonagem em uma thread separada
    thread = threading.Thread(target=processar_clonagem, args=(token, origem, destino))
    thread.start()
    return JSONResponse(content={"mensagem": "Iniciado"})

@app.get("/progresso")
async def progresso():
    # Rota que o celular vai consultar a cada 1 segundo via JavaScript
    return JSONResponse(content=status_clonagem)
    
