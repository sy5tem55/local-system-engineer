FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir docker prometheus-client
COPY exporter.py .
CMD ["python3", "-u", "exporter.py"]
