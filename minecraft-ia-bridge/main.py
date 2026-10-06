import asyncio
import json
import os
import uuid

import aiohttp
from aiohttp import web

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PREFIXO = os.environ.get("PREFIXO", "!ia ")
NOME_IA = os.environ.get("NOME_IA", "IA")
MAX_HISTORICO = 12
MAX_CHUNK = 180

SISTEMA = (
    f"Voce e {NOME_IA}, uma companheira amigavel dentro do Minecraft. "
    "Responda sempre em portugues do Brasil, de forma curta (no maximo 2 frases), "
    "sem markdown e sem emojis."
)


async def perguntar_gemini(http, historico):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"
    corpo = {
        "system_instruction": {"parts": [{"text": SISTEMA}]},
        "contents": historico,
    }
    headers = {"x-goog-api-key": GEMINI_API_KEY, "Content-Type": "application/json"}
    async with http.post(url, json=corpo, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as r:
        dados = await r.json()
        if r.status != 200:
            msg = dados.get("error", {}).get("message", "erro desconhecido")
            raise RuntimeError(f"Gemini {r.status}: {msg}")
    try:
        return dados["candidates"][0]["content"]["parts"][0]["text"].strip()
    except (KeyError, IndexError):
        return "Nao consegui responder agora."


def cabecalho(proposito, tipo="commandRequest"):
    return {
        "version": 1,
        "requestId": str(uuid.uuid4()),
        "messageType": tipo,
        "messagePurpose": proposito,
    }


async def enviar_chat(ws, texto):
    texto = " ".join(texto.split())
    partes = [texto[i:i + MAX_CHUNK] for i in range(0, len(texto), MAX_CHUNK)] or [""]
    for parte in partes:
        rawtext = json.dumps({"rawtext": [{"text": f"<{NOME_IA}> {parte}"}]}, ensure_ascii=False)
        await ws.send_json({
            "header": cabecalho("commandRequest"),
            "body": {
                "origin": {"type": "player"},
                "commandLine": f"tellraw @a {rawtext}",
                "version": 1,
            },
        })


def extrair_mensagem_chat(dados):
    header = dados.get("header") or {}
    body = dados.get("body") or {}
    event_name = header.get("eventName") or body.get("eventName")
    if event_name and event_name != "PlayerMessage":
        return None
    props = body.get("properties") or {}
    tipo = body.get("type") or props.get("MessageType") or props.get("type")
    texto = body.get("message") or props.get("Message") or props.get("message") or ""
    if tipo and str(tipo).lower() not in ("chat", "say"):
        return None
    if not texto:
        return None
    return str(texto)


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=None, compress=False, autoping=False)
    await ws.prepare(request)
    http = request.app["http"]
    historico = []

    print(
        "Conectou:",
        request.headers.get("User-Agent"),
        request.headers.get("Sec-WebSocket-Extensions"),
        flush=True,
    )

    try:
        await ws.send_json({
            "header": cabecalho("subscribe", "commandRequest"),
            "body": {"eventName": "PlayerMessage"},
        })
        print("Minecraft conectado (subscribe enviado).", flush=True)

        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.ERROR:
                print("WS error:", ws.exception(), flush=True)
                break
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            try:
                dados = json.loads(msg.data)
            except json.JSONDecodeError:
                continue

            texto = extrair_mensagem_chat(dados)
            if texto is None:
                continue
            if not texto.lower().startswith(PREFIXO.lower()):
                continue
            pergunta = texto[len(PREFIXO):].strip()
            if not pergunta:
                continue

            historico.append({"role": "user", "parts": [{"text": pergunta}]})
            try:
                resposta = await perguntar_gemini(http, historico)
            except Exception as e:
                historico.pop()
                resposta = f"Erro: {e}"
            else:
                historico.append({"role": "model", "parts": [{"text": resposta}]})
                del historico[:-MAX_HISTORICO]
            await enviar_chat(ws, resposta)
    finally:
        print("Fechou:", getattr(ws, "close_code", None), ws.exception(), flush=True)
        print("Minecraft desconectou.", flush=True)

    return ws


async def rota_raiz(request):
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await ws_handler(request)
    return web.Response(text="ok")


async def iniciar_http(app):
    app["http"] = aiohttp.ClientSession()


async def fechar_http(app):
    await app["http"].close()


def criar_app():
    app = web.Application()
    app.router.add_get("/", rota_raiz)
    app.router.add_get("/ws", ws_handler)
    app.on_startup.append(iniciar_http)
    app.on_cleanup.append(fechar_http)
    return app


if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("AVISO: defina a variavel GEMINI_API_KEY.", flush=True)
    web.run_app(criar_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
