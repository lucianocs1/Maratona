# Farol: API (FastAPI) e tela do app, como roda na máquina local, para produção (Render).
# - Mesmos pacotes do uv.lock (uv sync --frozen); Python da .python-version.
# - A voz local do aviso (Piper) é baixada no build e conferida pelo MD5 (apresentacao/audio.py): o servidor
#   não precisa de internet para falar, e o texto do aviso não sai dele. FAROL_VOZ_LOCAL=0 (build e execução)
#   deixa a voz local de fora: no plano gratuito do Render não há memória para ela (~520 MB a mais); o áudio
#   sai então só pela voz de nuvem (FAROL_VOZ_NUVEM=google e GOOGLE_TTS_KEY). FAROL_AUDIO=0 desliga todo o áudio.
# - Sem dados na imagem: a base territorial e a rede fictícia ficam no Postgres (DATABASE_URL).
# - Roda sem ser root. A porta vem de $PORT (o Render define). O IP real de quem acessa (limite de
#   tentativas de login) e o https vêm do proxy do Render pela própria API (api/proxy.py, só os itens
#   que o proxy acrescentou; FAROL_SALTOS_PROXY); o uvicorn não confia em X-Forwarded-* (--no-proxy-headers).
FROM python:3.12-slim
ARG FAROL_AUDIO=1
ARG FAROL_VOZ_LOCAL=1

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8 FAROL_PRODUCAO=1 FAROL_AUDIO=${FAROL_AUDIO} FAROL_VOZ_LOCAL=${FAROL_VOZ_LOCAL}

RUN useradd --create-home --uid 10001 farol
WORKDIR /app

# dependências primeiro (camada que só muda com o uv.lock)
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY distribuidoras ./distribuidoras
RUN uv sync --frozen --no-dev \
 && mkdir -p data saida \
 && if [ "$FAROL_AUDIO" != "0" ] && [ "$FAROL_VOZ_LOCAL" != "0" ]; then .venv/bin/python -c "from comunidades.apresentacao import audio; print(audio.garantir_voz())"; fi \
 && chown -R farol:farol /app

USER farol
ENV PATH="/app/.venv/bin:$PATH" PORT=10000
EXPOSE 10000
CMD ["sh", "-c", "exec uvicorn comunidades.api.app:app --host 0.0.0.0 --port ${PORT} --no-proxy-headers"]
