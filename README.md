# SOMIJI AI

A personal AI assistant by SOMIJI: a web interface plus a small Python backend. API keys stay on the server and never reach the browser.

## Run it

Requires Python 3.9+. There are no packages to install.

```
cd somiji-ai
cp .env.example .env     # add a key, or leave it empty for demo mode
python3 server.py
```

Open http://127.0.0.1:8000

## Configure (.env)

| Setting | Purpose |
|---|---|
| `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` | Enable those providers |
| `ANTHROPIC_MODELS`, `OPENAI_MODELS` | Comma-separated model names your account can use (the defaults are examples) |
| `OLLAMA_MODELS`, `OLLAMA_BASE_URL` | Local models through Ollama (install it and `ollama pull` a model first) |
| `HOST`, `PORT` | Default `127.0.0.1:8000` |

With no keys, only a demo model appears. It echoes your text and is not an AI.

## Features

Streaming chat, history with new and delete chat, model picker, image and text-file attachments (5 MB limit; text is cut at 100 KB), voice input and read-aloud (your browser's speech features), dark and light themes, your name and custom instructions, responsive layout. Chats and settings are stored in your browser, not on the server. Image data is not kept in saved history.

## Security

- Keys live only in the server's environment or `.env`. The browser only calls `/api/models` and `/api/chat`.
- The server listens on 127.0.0.1 and has no login. If you set `HOST=0.0.0.0` or deploy it, put it behind HTTPS and authentication, or anyone who can reach it can spend your API credit.
- Voice input needs localhost or HTTPS and a browser with speech recognition (Chrome, Edge, Safari).

## Status

Tested in a sandbox with no internet:
- Backend: model list, streamed chat in demo mode, the Anthropic and OpenAI-compatible/Ollama relays against local mock servers (including image payloads), unknown-model rejection, path traversal blocked, no key in served pages.
- UI in headless Chromium: loads without script errors, streamed reply renders, new chat, history survives reload, delete chat, light theme, attachment chip, mobile layout and sidebar.

Not tested: live calls to Anthropic, OpenAI or Ollama; microphone input and spoken playback; an image sent through a real model; Safari and Firefox; HTTPS or remote deployment.

Not included: agents and skills, document indexing and memory, scheduled briefings, connectors, desktop installers, server-side chat storage, PNG/ICO icon files (the logo is `static/logo.svg`).

## Layout

```
server.py          backend: static files, /api/models, /api/chat relay
static/index.html  the interface
static/logo.svg    logo and icon
.env.example       configuration template
```

## Credits

Inspired by the OpenJarvis project (Apache-2.0). SOMIJI AI is separate code and contains none of its code or branding.
