FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1
COPY requirements.txt requirements.txt
RUN uv pip install -r requirements.txt
RUN useradd -m -u 1000 bedrock_agentcore
USER bedrock_agentcore
EXPOSE 9000
COPY . .
CMD ["python", "-m", "agents.phase_4"]
