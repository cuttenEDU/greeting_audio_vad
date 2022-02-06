FROM ubuntu:focal

SHELL ["/bin/bash", "-c"]

WORKDIR /app

COPY pyproject.toml /app

RUN apt update && apt upgrade -y

ENV TZ=Europe/Moscow

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN DEBIAN_FRONTEND="noninteractive" apt-get -y install tzdata

RUN apt install -y curl

RUN apt install -y python3-pip python3 python-is-python3 python3-distutils python3-dev

RUN apt install -y gcc build-essential libpq-dev

RUN curl -sSL https://raw.githubusercontent.com/python-poetry/poetry/master/get-poetry.py | python -

RUN /root/.poetry/bin/poetry install

COPY . /app/

ENTRYPOINT /root/.poetry/bin/poetry run python launcher.py


