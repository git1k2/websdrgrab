# WebSDRgrab
WebSDR QRSS Grabber, grabs QRSS frames from WebSDR servers.

Work in progress ...

![QRSS Spectrogram](doc/20220818_184000.png)

## Local build, run, test
```
docker-compose build
docker-compose up -d
docker-compose logs -f websdrgrab
```
Find spectrograms and WAV files in the `./downloads/` directory.
