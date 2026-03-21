# OfficeQA Finance Agent — A2A-compatible Docker image
FROM python:3.11-slim-bookworm

# Create non-root user
RUN useradd -m agent
WORKDIR /home/agent/workspace

# Install dependencies first (layer caching)
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ src/

# Copy corpus (large — placed last for cache efficiency during dev)
# Note: corpus is mounted as volume in local dev; COPY is for full image builds
# COPY corpus/ /home/agent/corpus/

# Set environment defaults
ENV SERVER_PORT=9009
ENV SERVER_HOST=0.0.0.0
ENV CORPUS_DIR=/home/agent/corpus/transformed

# Expose A2A port
EXPOSE 9009

# Run the A2A server
USER agent
ENTRYPOINT ["python", "-m", "src.server"]
