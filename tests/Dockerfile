FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends g++ && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir esphome==2026.10.1
ENV PYTHONDONTWRITEBYTECODE=1
WORKDIR /src
