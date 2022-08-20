FROM debian:bullseye-slim

WORKDIR /app

RUN apt-get update \
&& apt-get install firefox-esr python3-pip -y \
&& apt-get clean

COPY config_dist.ini grab.py requirements.txt /app/

RUN pip install --user -r requirements.txt

CMD python3 ./grab.py