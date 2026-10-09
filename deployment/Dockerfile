FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-17-jre-headless libpq-dev gcc git curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir anvil-app-server \
    && if [ -s requirements.txt ]; then python -m pip install --no-cache-dir -r requirements.txt; fi

COPY . /app
RUN mkdir -p /data

EXPOSE 3030 80 443
VOLUME ["/data"]

CMD ["anvil-app-server", "--app", "/app", "--data-dir", "/data"]
