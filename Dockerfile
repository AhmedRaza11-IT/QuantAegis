# Multi-stage Windows Server Core Dockerfile
# Note: Since MT5 is Windows-only, this Dockerfile uses python:3.11-slim as a base,
# which is typically Linux, but a comment here explains the constraint. 
# Alternatively, a Wine-based Linux image could be used to run MT5 on Linux containers.
# Example: 
# FROM scottyhardy/docker-wine:latest
# RUN apt-get update && apt-get install -y python3 python3-pip

FROM python:3.11-slim as base

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENTRYPOINT ["python", "main.py"]
