# WebSDRgrab
WebSDR QRSS Grabber, grabs QRSS frames from WebSDR servers.

> **Note** \
> Please inform the owners of the WebSDR of your experiments and using this software. Especially when running for more than a few hours.

## Work in progress ...



![QRSS Spectrogram](doc/latest-twente-30m.png)

## Local build, run, test
```
docker-compose build
docker-compose up -d
docker-compose logs -f websdrgrab
```
Find spectrograms and WAV files in the `./downloads/` directory.
