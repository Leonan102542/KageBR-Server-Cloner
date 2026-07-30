import threading
import requests
import logging
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

app = FastAPI(title="KageBR Server Cloner")
templates = Jinja2Templates(directory="templates")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def processar_clonagem(token: str, origen_id: str, destino_id: str):
    # Cabeçalhos com User-Agent para evitar bloqueios de segurança do Discord
    headers = {
        "Authorization": token.strip(),
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    base_url = "https://discord.com"

    # 1. Buscar canais do servidor de origem
    res_canais = requests.get(f"{base_url}/guilds/{origen_id}/channels", headers=headers)
    if res_canais.status_code != 200:
        logging.error(f"Erro na origem: {res_canais.status_code}")
        return

    canais = res_canais.json()

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

    logging.info("Clonagem finalizada com sucesso.")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "status": None})

# CORRIGIDO: Agora a rota retorna a página HTML estilizada com o status em vez de JSON puro
@app.post("/clonar", response_class=HTMLResponse)
async def clonar(request: Request, token: str = Form(...), origem: str = Form(...), destino: str = Form(...)):
    # Dispara o processo em segundo plano para o navegador não dar timeout
    thread = threading.Thread(target=processar_clonagem, args=(token, origem, destino))
    thread.start()
    
    status_msg = "Clonagem iniciada com sucesso! Verifique os canais surgindo no seu aplicativo do Discord."
    return templates.TemplateResponse("index.html", {"request": request, "status": status_msg})
    
