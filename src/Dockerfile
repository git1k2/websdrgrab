FROM debian:bullseye-slim

WORKDIR /app

# Install required packages
RUN apt-get update \
&& apt-get install bzip2 curl libasound2 procps python3-pip -y \
&& apt-get clean

# Copy app files
COPY config_dist.ini grab.py requirements.txt /app/

# Install python requirements
RUN pip install --user -r requirements.txt

# Download and extract latest firefox
RUN curl -sL "https://download.mozilla.org/?product=firefox-latest-ssl&os=linux64" | tar -xj -C /opt

# Download and extract geckodriver 
RUN curl -sL "https://github.com/mozilla/geckodriver/releases/download/v0.31.0/geckodriver-v0.31.0-linux64.tar.gz" | tar -xz -C /usr/local/bin 

CMD python3 ./grab.py