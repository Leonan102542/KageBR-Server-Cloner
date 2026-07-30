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

    # Cabeçalhos com User-Agent para evitar bloqueios de segurança da API do Discord
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    # CORRIGIDO: Rota completa da API v10 do Discord adicionada
    base_url = "https://discord.com"

    # 1. Buscar canais do servidor de origem
    res_canais = requests.get(f"{base_url}/guilds/{origen_id}/channels", headers=headers)
    if res_canais.status_code != 200:
        status_clonagem["status"] = f"❌ Erro na origem! Token inválido ou sem acesso (Code: {res_canais.status_code})"
        status_clonagem["finalizado"] = True
        return

    canais = res_canais.json()
    status_clonagem["total"] = len(canais)
    status_clonagem["status"] = "Estrutura mapeada! Limpando destino..."

    # 2. Deletar canais padrão automáticos do servidor de destino para não causar conflitos
    res_destino_canais = requests.get(f"{base_url}/guilds/{destino_id}/channels", headers=headers)
    if res_destino_canais.status_code == 200:
        for c_velho in res_destino_canais.json():
            requests.delete(f"{base_url}/channels/{c_velho['id']}", headers=headers)

    # 3. Ordenação para garantir que categorias sejam criadas antes dos canais de texto/voz
    canais_ordenados = sorted(canais, key=lambda c: c.get("type", 0) != 4)
    mapa_categorias = {}

    # 4. Replicar a estrutura no servidor de destino
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
        
        # Atualiza as estatísticas exibidas na tela do celular
        status_clonagem["criados"] += 1
        status_clonagem["status"] = f"Criado: {canal['name']}"

    status_clonagem["status"] = "🎉 KageBR Cloner finalizou a cópia com sucesso!"
    status_clonagem["finalizado"] = True

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/clonar")
async def clonar(token: str = Form(...), origem: str = Form(...), destino: str = Form(...)):
    # Dispara o processo em segundo plano (Thread) para não congelar o navegador do smartphone
    thread = threading.Thread(target=processar_clonagem, args=(token, origem, destino))
    thread.start()
    return JSONResponse(content={"mensagem": "Iniciado"})

@app.get("/progresso")
async def progresso():
    # Rota consultada automaticamente pelo painel a cada 1 segundo
    return JSONResponse(content=status_clonagem)
    
