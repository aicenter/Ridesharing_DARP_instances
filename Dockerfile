# Instance builder service (web/graph-editor/server) for Google Cloud Run.
# Build context: the repository root (the service needs JSON/instance_spec.schema.json).
#
#   docker build -t darp-builder . && docker run --rm -p 8080:8080 darp-builder
#
# The image tag must equal the playwright version in web/graph-editor/package-lock.json:
# it ships the matching Chromium and its system libraries.
FROM mcr.microsoft.com/playwright:v1.63.0-noble

WORKDIR /app

COPY web/graph-editor/package.json web/graph-editor/package-lock.json web/graph-editor/
RUN cd web/graph-editor && npm ci

COPY JSON/instance_spec.schema.json JSON/
COPY web/graph-editor web/graph-editor
RUN cd web/graph-editor && npm run build

ENV NODE_ENV=production PORT=8080
EXPOSE 8080
WORKDIR /app/web/graph-editor
CMD ["npx", "tsx", "server/main.ts"]
