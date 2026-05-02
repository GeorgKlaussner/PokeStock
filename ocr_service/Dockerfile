FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-deu \
        tesseract-ocr-eng \
        tesseract-ocr-jpn \
        tesseract-ocr-spa \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /service
COPY ocr_service/server.py .

EXPOSE 8080

CMD ["python", "server.py"]
