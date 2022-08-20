FROM debian:bullseye-slim

WORKDIR /app

# Install required packages. Also installing firefox here to get
# dependencies installed. Will be downloading the latest firefox
# below and using it. This is configured in config_dist.ini.
ARG DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
  && apt install bzip2 curl firefox-esr libasound2 procps python3-pip -y \
  && apt clean

# Install python requirements
COPY requirements.txt /app/
RUN pip install --user -r requirements.txt

# Download and extract latest firefox
RUN curl -sL "https://download.mozilla.org/?product=firefox-latest-ssl&os=linux64" | tar -xj -C /opt

# Download and extract geckodriver 
RUN curl -sL "https://github.com/mozilla/geckodriver/releases/download/v0.31.0/geckodriver-v0.31.0-linux64.tar.gz" | tar -xz -C /usr/local/bin 

# Copy app files
COPY config*.ini grab.py /app/

CMD python3 ./grab.py