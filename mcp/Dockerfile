# The hosted service. Build from the repository root: docker build -f mcp/Dockerfile -t bestpred-mcp .
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md LICENSE NOTICE ./
COPY src ./src
COPY mcp ./mcp
RUN pip install --no-cache-dir ./ ./mcp && useradd --create-home bestpred
USER bestpred
ENV PORT=8080
EXPOSE 8080
CMD ["bestpred-mcp", "--http", "--host", "0.0.0.0"]
