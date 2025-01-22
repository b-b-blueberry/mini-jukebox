FROM python:3.12-alpine

RUN apk add \
    build-base \
    ffmpeg \
    libffi-dev \
    opus-dev \
    sqlite

ADD requirements.txt /jukebox/requirements.txt
RUN pip3 install -r /jukebox/requirements.txt

CMD ["python3", "-u", "/jukebox/main.py"]
