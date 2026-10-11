FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN pip install --no-cache-dir --no-deps .
EXPOSE 3000
CMD ["uvicorn", "openapi_server.main:app", "--host", "0.0.0.0", "--port", "3000", "--ws-ping-interval", "15", "--ws-ping-timeout", "30"]
