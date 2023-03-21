# pull official base image
FROM python:3.10.8-slim-buster
MAINTAINER Tor <gauss.ind@gmail.com>

# set working directory
WORKDIR /orders

# set environment variables
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# install dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY ./requirements.txt .
RUN pip install --upgrade --no-cache -r requirements.txt


# add app
COPY . .
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
