import asyncio
import json
import os
import uuid

import aiohttp
from aiohttp import web

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
# Se o nome do modelo mudar, basta trocar a variável GEMINI_MODEL no Render.
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PREFIXO = os.environ.get("PREFIXO", "!ia ")
NOME_IA = os.environ.get("NOME_IA", "IA")
MAX_HISTORICO = 12  # mensagens lembradas (user + model)
MAX_CHUNK = 180  # tamanho máximo de cada linha enviada ao chat

SISTEMA = (
    f"Você é {NOME_IA}, uma companheira amigável dentro do Minecraft. "
    "Responda sempre em português do Brasil, de forma curta (no máximo 2 frases), "
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
        return "Não consegui responder agora."


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


async def ws_handler(request):
    ws = web.WebSocketResponse(heartbeat=30)
    await ws.prepare(request)
    http = request.app["http"]
    historico = []

    # Pede ao Minecraft para avisar quando alguém escrever no chat
    await ws.send_json({
        "header": cabecalho("subscribe", "commandRequest"),
        "body": {"eventName": "PlayerMessage"},
    })
    print("Minecraft conectado.")

    async for msg in ws:
        if msg.type != aiohttp.WSMsgType.TEXT:
            continue
        try:
            dados = json.loads(msg.data)
        except json.JSONDecodeError:
            continue

        if dados.get("header", {}).get("eventName") != "PlayerMessage":
            continue
        corpo = dados.get("body", {})
        # Só mensagens de chat reais (ignora as que o próprio bot enviou via tellraw)
        if corpo.get("type") != "chat":
            continue
        texto = corpo.get("message", "")
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

    print("Minecraft desconectou.")
    return ws


async def saude(request):
    return web.Response(text="ok")


async def iniciar_http(app):
    app["http"] = aiohttp.ClientSession()


async def fechar_http(app):
    await app["http"].close()


def criar_app():
    app = web.Application()
    app.router.add_get("/", saude)
    app.router.add_get("/ws", ws_handler)
    app.on_startup.append(iniciar_http)
    app.on_cleanup.append(fechar_http)
    return app


if __name__ == "__main__":
    if not GEMINI_API_KEY:
        print("AVISO: defina a variável GEMINI_API_KEY.")
    web.run_app(criar_app(), host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))