FROM python:3.11-slim

WORKDIR /app
COPY loadgen.py /app/loadgen.py

ENV PYTHONUNBUFFERED=1

CMD ["python", "/app/loadgen.py"]
