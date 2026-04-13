# OfficeQA Finance Agent — A2A-compatible Docker image
FROM python:3.11-slim-bookworm

# Create non-root user
RUN useradd -m agent
WORKDIR /home/agent/workspace

# Install dependencies first (layer caching)
# Note: Since the build context is the parent directory (Option B), we prefix with workspace/
COPY workspace/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY workspace/src/ src/

# Copy the skills from agentspace into the correct container path
# harness.py resolves agentspace relative to workspace folder!
COPY agentspace/skills/ /home/agent/agentspace/skills/

# Copy corpus (large — placed last for cache efficiency during dev)
# Note: corpus is mounted as volume in local dev; COPY is for full image builds
COPY corpus/ /home/agent/corpus/

# Set environment defaults
ENV SERVER_PORT=9009
ENV SERVER_HOST=0.0.0.0
ENV CORPUS_DIR=/home/agent/corpus/transformed

# Ensure the agent user owns everything it needs to read/write at runtime.
# Scratch must exist and be writable; workspace and corpus must be readable.
RUN mkdir -p /home/agent/agentspace/scratch \
 && chown -R agent:agent /home/agent/agentspace /home/agent/workspace /home/agent/corpus

# Expose A2A port
EXPOSE 9009

# Run the A2A server
USER agent
ENTRYPOINT ["python", "-m", "src.server"]
