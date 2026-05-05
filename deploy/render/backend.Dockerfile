FROM haskell:9.12.2-slim-bookworm AS haskell-builder

WORKDIR /build

COPY services/ontology-hs/ontology-hs.cabal services/ontology-hs/ontology-hs.cabal
WORKDIR /build/services/ontology-hs
RUN cabal update

COPY services/ontology-hs/app app
COPY services/ontology-hs/src src
RUN cabal build -v0 exe:ontology-hs \
    && mkdir -p /out/bin \
    && cp "$(cabal list-bin -v0 exe:ontology-hs)" /out/bin/ontology-hs

FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NBA_ONTOLOGY_PLANNER_BIN=/app/bin/ontology-hs \
    NBA_DISABLE_SNAPSHOT_REBUILD=1 \
    LLM_INTERPRETER_PROVIDER=google \
    LLM_INTERPRETER_TEMPERATURE=0 \
    LLM_INTERPRETER_ATTEMPTS_PER_MODEL=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libffi8 libgmp10 libncurses6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=haskell-builder /out/bin/ontology-hs /app/bin/ontology-hs
COPY apps/__init__.py apps/__init__.py
COPY apps/assistant apps/assistant
COPY apps/web apps/web
COPY services/runtime-py services/runtime-py
COPY scripts/__init__.py scripts/__init__.py
COPY scripts/load_gold_snapshot.py scripts/load_gold_snapshot.py
COPY fixtures/ontology fixtures/ontology
COPY fixtures/duckdb/gold_slice.duckdb fixtures/duckdb/gold_slice.duckdb

RUN /app/bin/ontology-hs validate-ontology-json --ontology /app/fixtures/ontology/semantic-gold.yaml \
    && python -m compileall -q apps services/runtime-py scripts

EXPOSE 10000

CMD ["sh", "-c", "uvicorn apps.web.server:app --host 0.0.0.0 --port ${PORT:-10000}"]
