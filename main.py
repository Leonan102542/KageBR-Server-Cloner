import threading
import time
import json
import asyncio
import base64
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.websockets import WebSocket, WebSocketDisconnect
import requests

app = FastAPI(title="KageBR Server Cloner Enterprise")
templates = Jinja2Templates(directory="templates")

API_BASE = "https://discord.com"

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try: await connection.send_text(message)
            except Exception: pass

manager = ConnectionManager()

def enviar_log(mensagem: str):
    try: loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    loop.create_task(manager.broadcast(mensagem))

def executar_fluxo_clonagem(token: str, origem_id: str, destino_id: str):
    # Uso de requests.Session para Keep-Alive (Melhoria de Performance de Rede)
    with requests.Session() as sess:
        sess.headers.update({
            "Authorization": token,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Content-Type": "application/json"
        })
        
        def requisicao_segura(metodo: str, url: str, json_data: dict = None) -> requests.Response:
            erros_autenticacao = 0
            while True:
                try:
                    if metodo == "GET": res = sess.get(url, timeout=12)
                    elif metodo == "POST": res = sess.post(url, json=json_data, timeout=12)
                    elif metodo == "DELETE": res = sess.delete(url, timeout=12)
                    
                    # Circuit Breaker: previne ban de IP por requisições inválidas sequenciais
                    if res.status_code in [401, 403]:
                        erros_autenticacao += 1
                        if erros_autenticacao >= 3:
                            enviar_log("🚨 [CRÍTICO] Falha de autenticação repetida. Operação abortada para evitar ban na Cloudflare!")
                            raise PermissionError()
                    
                    if res.status_code == 429:
                        tempo = res.json().get("retry_after", 2.0)
                        enviar_log(f"⚠️ Limite atingido. Pausando fluxo por {tempo}s...")
                        time.sleep(tempo + 0.1)
                        continue
                    return res
                except requests.RequestException:
                    enviar_log("⚡ Instabilidade na rede. Nova tentativa em 3s...")
                    time.sleep(3)

        try:
            # 1. Higienização do Destino
            enviar_log("🔄 Iniciando varredura e higienização do destino...")
            res = requisicao_segura("GET", f"{API_BASE}/guilds/{destino_id}/channels")
            if res.status_code == 200:
                canais = res.json()
                for idx, c in enumerate(canais, 1):
                    enviar_log(f"🗑️ Eliminando canal padrão [{idx}/{len(canais)}]: #{c.get('name')}")
                    requisicao_segura("DELETE", f"{API_BASE}/channels/{c['id']}")
                    time.sleep(0.2)

            mapa_cargos, mapa_categorias = {}, {}

            # 2. Replicar Cargos
            enviar_log("🎭 Extraindo mapa de cargos da origem...")
            res_roles = requisicao_segura("GET", f"{API_BASE}/guilds/{origem_id}/roles")
            if res_roles.status_code == 200:
                for cargo in reversed(res_roles.json()):
                    if cargo.get("managed") or cargo.get("name") == "@everyone": continue
                    payload = {"name": cargo.get("name"), "permissions": cargo.get("permissions"), "color": cargo.get("color"), "hoist": cargo.get("hoist"), "mentionable": cargo.get("mentionable")}
                    res_c = requisicao_segura("POST", f"{API_BASE}/guilds/{destino_id}/roles", json_data=payload)
                    if res_c.status_code in [200, 201]:
                        mapa_cargos[cargo["id"]] = res_c.json()["id"]
                        enviar_log(f"✅ Cargo replicado: {cargo.get('name')}")
                    time.sleep(0.2)

            # 3. Replicar Emojis
            enviar_log("✨ Capturando biblioteca de emojis da origem...")
            res_emojis = requisicao_segura("GET", f"{API_BASE}/guilds/{origem_id}/emojis")
            if res_emojis.status_code == 200:
                for em in res_emojis.json():
                    try:
                        img_res = sess.get(f"https://discordapp.com{em['id']}.png", timeout=8)
                        if img_res.status_code == 200:
                            b64 = base64.b64encode(img_res.content).decode('utf-8')
                            payload = {"name": em["name"], "image": f"data:image/png;base64,{b64}"}
                            res_e = requisicao_segura("POST", f"{API_BASE}/guilds/{destino_id}/emojis", json_data=payload)
                            if res_e.status_code in [200, 201]: enviar_log(f"✅ Emoji injetado: :{em['name']}:")
                    except Exception: pass
                    time.sleep(0.2)

            # 4. Estruturar Canais
            enviar_log("📂 Analisando estrutura arquitetônica de canais...")
            res_ch = requisicao_segura("GET", f"{API_BASE}/guilds/{origem_id}/channels")
            if res_ch.status_code != 200: return
            
            canais = res_ch.json()
            categorias = [c for c in canais if c.get("type") == 4]
            outros_canais = [c for c in canais if c.get("type") != 4]
            
            def traduzir_permissoes(overwrites):
                novas = []
                for ow in overwrites:
                    id_alvo = ow["id"]
                    if ow["type"] == 0: id_alvo = mapa_cargos.get(id_alvo, id_alvo)
                    novas.append({"id": id_alvo, "type": ow["type"], "allow": ow["allow"], "deny": ow["deny"]})
                return novas

            # Categorias primeiro
            for cat in categorias:
                payload = {"name": cat.get("name"), "type": 4, "position": cat.get("position"), "permission_overwrites": traduzir_permissoes(cat.get("permission_overwrites", []))}
                res_cat = requisicao_segura("POST", f"{API_BASE}/guilds/{destino_id}/channels", json_data=payload)
                if res_cat.status_code in [200, 201]:
                    mapa_categorias[cat["id"]] = res_cat.json()["id"]
                    enviar_log(f"📁 Categoria posicionada: {cat.get('name')}")
                time.sleep(0.2)

            # Canais de Texto/Voz aninhados com Purificação de Payload (Otimização de tráfego)
            for canal in outros_canais:
                payload = {
                    "name": canal.get("name"), "type": canal.get("type"), "position": canal.get("position"),
                    "topic": canal.get("topic"), "nsfw": canal.get("nsfw"), "bitrate": canal.get("bitrate"),
                    "user_limit": canal.get("user_limit"), "parent_id": mapa_categorias.get(canal.get("parent_id")),
                    "permission_overwrites": traduzir_permissoes(canal.get("permission_overwrites", []))
                }
                payload = {k: v for k, v in payload.items() if v is not None} # Limpeza de chaves nulas
                res_canal = requisicao_segura("POST", f"{API_BASE}/guilds/{destino_id}/channels", json_data=payload)
                if res_canal.status_code in [200, 201]: enviar_log(f"🔗 Canal integrado: #{canal.get('name')}")
                time.sleep(0.2)

            enviar_log("🎉 OPERAÇÃO FINALIZADA COM SUCESSO ABSOLUTO!")
        except PermissionError: pass
        except Exception: enviar_log("❌ Erro imprevisto no núcleo da automação.")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/clonar")
async def clonar(token: str = Form(...), origem_id: str = Form(...), destino_id: str = Form(...)):
    threading.Thread(target=executar_fluxo_clonagem, args=(token, origem_id, destino_id)).start()
    return {"status": "processing"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True: await websocket.receive_text()
    except WebSocketDisconnect: manager.disconnect(websocket)
        
