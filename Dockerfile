FROM python:3.12-alpine

RUN apk add \
    build-base \
    ffmpeg \
    libffi-dev \
    opus-dev \
    sqlite

RUN mkdir /jukebox
ADD requirements.txt /jukebox
ADD src /jukebox
WORKDIR /jukebox
RUN pip3 install -r requirements.txt
CMD ["python", "-u", "main.py"]
