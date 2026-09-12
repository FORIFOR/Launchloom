FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright \
    LAUNCHLOOM_HOST=0.0.0.0 LAUNCHLOOM_PORT=8787 \
    LAUNCHLOOM_DATA=/data CHROMIUM_EXECUTABLE=/usr/bin/chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg chromium fonts-noto-cjk ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY . .
RUN pip install --no-cache-dir . && python -m playwright install ffmpeg \
    && useradd --create-home --uid 10001 studio \
    && mkdir -p /data && chown -R studio:studio /data /opt/playwright
USER studio
EXPOSE 8787
CMD ["python", "-m", "launchloom", "serve"]
