FROM ghcr.io/astral-sh/uv:python3.12-alpine

RUN apk add \
    build-base \
    ffmpeg \
    libffi-dev \
    opus-dev \
    sqlite

ADD src /jukebox
ADD uv.lock /jukebox
ADD pyproject.toml /jukebox

WORKDIR /jukebox
RUN uv sync --frozen
CMD ["uv", "run", "main.py"]
