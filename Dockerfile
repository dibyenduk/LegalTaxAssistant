FROM mcr.microsoft.com/devcontainers/python:3.11

WORKDIR /app

COPY src/mcp_server/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/mcp_server/ ./mcp_server/

EXPOSE 8080

CMD ["python", "-m", "mcp_server.server"]
