FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1     PYTHONUNBUFFERED=1     PYTHONPATH=/app/vendor-evaluation/vindex:/app

WORKDIR /app

RUN apt-get update     && apt-get install -y --no-install-recommends ffmpeg git     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN useradd --create-home --uid 10001 mvi     && mkdir -p /var/lib/mvi     && chown -R mvi:mvi /app /var/lib/mvi

USER mvi
EXPOSE 10000
CMD ["python", "render_entrypoint.py"]
