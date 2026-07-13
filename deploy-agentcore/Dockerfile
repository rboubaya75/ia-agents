FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt

RUN useradd --create-home --uid 1000 bedrock_agentcore
COPY --chown=bedrock_agentcore:bedrock_agentcore . .

USER bedrock_agentcore
EXPOSE 8080
CMD ["python", "-m", "agents.phase_4_robust"]
