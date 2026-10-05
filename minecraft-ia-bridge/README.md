# Minecraft IA Bridge

Este diretório contém um pequeno servidor em Python para conectar o Minecraft Bedrock ao Gemini.

## Objetivo

- O Minecraft abre uma conexão WebSocket para este servidor
- O servidor escuta mensagens do chat com o prefixo `!ia `
- Envia a pergunta para a API Gemini
- Responde de volta no chat do Minecraft

## Estrutura

- `main.py` — servidor WebSocket + integração com Gemini
- `requirements.txt` — dependências do projeto

## Deploy no Render

1. Crie um novo Web Service no Render
2. Conecte este repositório
3. Defina a pasta raiz como:
   - `minecraft-ia-bridge`
4. Configuração do build:
   - `pip install -r requirements.txt`
5. Configuração do start:
   - `python main.py`
6. Adicione a variável de ambiente:
   - `GEMINI_API_KEY` = a sua chave da API do Gemini
7. Opcionalmente, pode definir:
   - `GEMINI_MODEL` = `gemini-2.5-flash`
   - `PREFIXO` = `!ia `
   - `NOME_IA` = `IA`

## Como usar no Minecraft Bedrock

No jogo, execute o comando:

```
/connect <URL_DO_RENDER>
```

Exemplo:

```
/connect https://seu-app.onrender.com/ws
```

Depois, no chat:

```
!ia qual é a melhor mina para começar?
```

A IA responderá no chat do servidor.

## Observações

- Este projeto não inclui Behavior Pack nem Script API do Minecraft
- O foco aqui é apenas a ponte web server em Python para o Render
- O servidor usa `aiohttp` para websockets e requisições HTTP
