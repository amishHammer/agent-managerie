FROM python:3.13-alpine

WORKDIR /app

COPY python /app/python

ENV PYTHONPATH=/app/python

CMD ["python", "-m", "menagerie.collector"]
