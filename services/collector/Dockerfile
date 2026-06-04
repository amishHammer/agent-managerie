# SPDX-License-Identifier: AGPL-3.0-only

FROM python:3.13-alpine

LABEL org.opencontainers.image.licenses="AGPL-3.0-only"

WORKDIR /app

COPY python /app/python

ENV PYTHONPATH=/app/python

CMD ["python", "-m", "menagerie.collector"]
