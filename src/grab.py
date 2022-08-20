import concurrent.futures
import configparser
import logging
import matplotlib.pyplot as plt
import numpy as np
import os
import paramiko
import random
import sched
import selenium.common.exceptions
import time

from datetime import datetime, timedelta, timezone
from pathlib import Path
from scipy.io import wavfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options


def create_spectrogram(wav_file=None, output_file_path=None, next_run=None, start_time=None, spec_config=None):
    logging.info(f"Run [{next_run}] creating spectrogram {Path(output_file_path).name}")

    # Defaults if not set in config.ini
    colormap = 'jet'
    spec_nfft = 16384
    spec_vmin = 30
    spec_vmax = 100
    min_freq_hz = 300
    max_freq_hz = 2500
    base_freq_hz = 0
    spec_noverlap = spec_nfft / 2
    title = "No title set in config.ini"
    subtitle = "No subtitle set in config.ini"

    # Retrieve settings.
    if spec_config:
        colormap = spec_config.get('spec_colormap', fallback=colormap)
        spec_nfft = spec_config.getint('spec_nfft', fallback=spec_nfft)
        spec_vmin = spec_config.getint('spec_vmin', fallback=spec_vmin)
        spec_vmax = spec_config.getint('spec_vmax', fallback=spec_vmax)
        spec_noverlap = spec_config.getint('spec_noverlap', fallback=spec_noverlap)
        base_freq_hz = spec_config.getint('base_freq_hz', fallback=base_freq_hz)
        min_freq_hz = spec_config.getint('min_freq_hz', fallback=min_freq_hz) - base_freq_hz
        max_freq_hz = spec_config.getint('max_freq_hz', fallback=max_freq_hz) - base_freq_hz
        title = spec_config.get('title', fallback=title)
        subtitle = spec_config.get('subtitle', fallback=subtitle)

    # Set colors (dark theme).
    plt.rcParams['axes.facecolor'] = 'black'
    plt.rcParams['savefig.facecolor'] = 'black'
    plt.rcParams['axes.edgecolor'] = 'white'
    plt.rcParams['lines.color'] = 'white'
    plt.rcParams['text.color'] = 'white'
    plt.rcParams['xtick.color'] = 'white'
    plt.rcParams['ytick.color'] = 'white'
    plt.rcParams['axes.labelcolor'] = 'white'

    # Create figure with specific size and DPI.
    plt.figure(num=None, figsize=(13, 8), dpi=100)

    # Read the WAV file.
    sampling_frequency, signal_data = wavfile.read(wav_file)

    # Instantiate spectrogram
    Pxx, freqs, bins, im = plt.specgram(
        signal_data,
        Fs=sampling_frequency,
        NFFT=spec_nfft,
        vmin=spec_vmin,
        vmax=spec_vmax,
        noverlap=spec_noverlap,
        cmap=colormap,
    )

    # Limit frequency range.
    plt.ylim(bottom=min_freq_hz, top=max_freq_hz)

    # Add title and labels.
    plt.title(title, loc='left', fontsize=16)
    plt.title(subtitle, loc='right', fontsize=13, color='grey')

    plt.xlabel(f'Start time: {start_time} UTC')
    plt.ylabel('Frequency, Hz')
    cbar = plt.colorbar()
    cbar.ax.set_ylabel('dB')

    # Y Labels
    ticks, labels = plt.yticks()
    for i, t in enumerate(ticks):
        new_freq = f"{int(t + base_freq_hz):,d}"
        # A Thousand separator is a dot here.
        labels[i].set_text(new_freq.replace(',', '.'))
    plt.yticks(ticks, labels)

    # X Labels
    length = signal_data.shape[0] / sampling_frequency
    plt.xticks(np.arange(0, round(length)+1, step=60))
    ticks, labels = plt.xticks()
    for i, t in enumerate(ticks):
        xtick_time = start_time.timestamp() + t
        labels[i].set_text(datetime.fromtimestamp(xtick_time, tz=timezone.utc).strftime('%H:%M'))
    plt.xticks(ticks, labels)

    # Save figure.
    plt.savefig(output_file_path, bbox_inches='tight')
    plt.close()


def upload_latest_png_sftp(config):
    config_default = config['DEFAULT']
    download_dir = Path(config_default.get('download_dir', fallback="downloads"))
    try:
        config_sftp = config['sftp']
    except KeyError:
        logging.info("SFTP not configured in config.ini, skipping upload")
        return

    host = config_sftp.get('host')
    port = config_sftp.getint('port', fallback=22)
    username = config_sftp.get('username')
    password = config_sftp.get('password')
    dest_path = config_sftp.get('dest_path')

    # Get the latest PNG file
    downloads = download_dir.glob('*.png')
    latest_file = max(downloads, key=os.path.getctime)

    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(hostname=host, port=port, username=username, password=password)
    sftp = ssh.open_sftp()

    try:
        sftp.put(str(latest_file), dest_path)
    except FileNotFoundError as err:
        logging.error(f"{err} {dest_path}")
    except PermissionError as err:
        logging.error(f"{err} {dest_path}")
    finally:
        sftp.close()
        ssh.close()


def spawn_rec_and_process(pool, config, next_run):
    pool.submit(record_and_process, config, next_run)


def record_and_process(config, next_run):
    logging.info(f"Run [{next_run}] Starting thread")
    record(config, next_run)

    # Wait a random amount of seconds before generating the spectrogram, this
    # flattens the CPU spike when running multiple grabbers.
    time.sleep(random.randint(2, 10))
    process(config, next_run)

    # Upload the spectrogram.
    upload_latest_png_sftp(config)

    # Delete old files.
    config_default = config['DEFAULT']
    download_dir = Path(config_default.get('download_dir', fallback='downloads'))
    max_file_age = config_default.get('max_file_age', fallback=7)
    if not download_dir.is_absolute():
        download_dir = Path(Path(__file__).parent, download_dir)
    delete_old_files(download_dir, max_file_age)

    logging.info(f"Run [{next_run}] Thread finished")


def record(config, next_run):
    config_firefox = config['firefox']
    config_websdr = config['websdr']

    # Configure download directory
    config_default = config['DEFAULT']
    download_dir = Path(config_default.get('download_dir', fallback='downloads'))
    if not download_dir.is_absolute():
        download_dir = Path(Path(__file__).parent, download_dir)
    download_dir.mkdir(exist_ok=True)

    # Configure browser, headless, download directory, etc...
    options = Options()
    options.headless = config_firefox.getboolean('firefox_headless', fallback=True)
    if config_firefox.get('firefox_location'):
        options.binary_location = config_firefox.get('firefox_location')
    
    # Debug level in geckodriver.log
    if logging.root.level < logging.DEBUG:
        options.log.level = "trace"
    
    options.set_preference("browser.download.folderList", 2)
    options.set_preference("browser.download.manager.showWhenStarting", False)
    options.set_preference("browser.download.dir", str(download_dir))
    options.set_preference("browser.helperApps.neverAsk.saveToDisk", "audio/wav, audio/x-wav")
    options.set_preference("browser.helperApps.alwaysAsk.force", False)
    options.set_preference("browser.download.useDownloadDir", True)

    # Start browser
    driver = webdriver.Firefox(options=options)
    try:
        logging.info(f"Run [{next_run}] Starting browser")
        complete_url = f"{config_websdr.get('url')}"
        driver.get(complete_url)
        assert config_websdr.get('in_title') in driver.title
    except Exception as err:
        driver.close()
        raise

    # Configure
    logging.info(f"Run [{next_run}] Configuring browser, session ID: {driver.session_id}")
    tries = 0
    while True and driver.session_id:
        try:
            tries += 1
            if tries > 5:
                break

            frequency = config_websdr.getint('base_freq_hz') / 1000
            mode = 0  # USB
            lo = config_websdr.get('lo')
            hi = config_websdr.get('hi')

            band = config_websdr.getint('band', fallback=0)
            soundapplet_params = f"f={frequency}&band={band}&lo={lo}&hi={hi}&mode={mode}"

            # Sometimes settings are not set? The received audio is not from the
            # requested frequency. Did not yet found a way to query the server.
            # Try 3 times, with 1/2 second pause.
            for _ in range(3):
                # Set volume to zero, mute will also mute the recording.
                logging.info('Set volume to 0')
                driver.execute_script(f"soundapplet.setvolume('0');")

                # Disable waterfall (blind mode).
                logging.info('Disable waterfall')
                driver.execute_script("setview(3);")

                # Set frequency, mode, band, width.
                logging.info(f"Set params: {soundapplet_params}")
                driver.execute_script(f'soundapplet.setparam("{soundapplet_params}");')

                # Resume audio
                logging.info('Resume audio')
                driver.execute_script("soundapplet.audioresume();")

                time.sleep(0.5)

            # Schedule recording session.
            s = sched.scheduler(time.time, time.sleep)
            config_schedule = config['schedule']
            slot_length_min = config_schedule.getint('slot_length_min', fallback=10)
            config_time_sec = config_schedule.getint('config_time_sec')
            record_start = next_run + timedelta(seconds=config_time_sec)
            record_stop = record_start + timedelta(minutes=slot_length_min)
            logging.info(f"Run [{next_run}] Start recording at: {record_start}")
            logging.info(f"Run [{next_run}] Stop recording at:  {record_stop}")

            s.enterabs(record_start.timestamp(), 0, driver.execute_script, argument=("record_start();",))
            s.enterabs(record_stop.timestamp(), 0, driver.execute_script, argument=("record_stop();",))
            s.run()

            logging.info(f"Run [{next_run}] Downloading audio")

            for link_text in ["save", "download"]:
                try:
                    # Click the download link.
                    link = driver.find_element(By.LINK_TEXT, link_text)
                    link.click()

                    # Wait until download has finished.
                    time.sleep(5)
                    break
                except selenium.common.exceptions.NoSuchElementException:
                    pass

            # If we got this far, break the while loop.
            break

        except selenium.common.exceptions.JavascriptException as err:
            # Got a Javascript exception, trying again...
            logging.error(err)
            time.sleep(1)

    # Close browser.
    logging.info(f"Run [{next_run}] Closing browser")
    driver.close()


def process(config, next_run):
    # Configure download directory
    config_default = config['DEFAULT']
    config_spectrogram = config['spectrogram']
    config_websdr = config['websdr']

    # Copy base frequency to spec settings
    config_spectrogram['base_freq_hz'] = config_websdr.get('base_freq_hz')

    download_dir = Path(config_default.get('download_dir', fallback='downloads'))
    if not download_dir.is_absolute():
        download_dir = Path(Path(__file__).parent, download_dir)
    download_dir.mkdir(exist_ok=True)

    # Get the latest file
    downloads = download_dir.glob('*.wav')
    latest_file = max(downloads, key=os.path.getctime)

    config_schedule = config['schedule']
    config_time_sec = config_schedule.getint('config_time_sec')

    # Record starts when configuring is done.
    record_start = next_run + timedelta(seconds=config_time_sec)

    filename_timestamp = record_start.strftime("%Y%m%d_%H%M%S")

    # The download filename is wrong. It is based on website's variables, which we don't use.
    # Here we rename the WAV file.
    latest_file = latest_file.rename(Path(download_dir, f"{filename_timestamp}.wav"))
    logging.info(f"Run [{next_run}] Latest file is: {latest_file.name}")

    output_filename = f"{filename_timestamp}.png"
    output_file_path = Path(download_dir, output_filename)

    create_spectrogram(
        wav_file=latest_file,
        output_file_path=output_file_path,
        next_run=next_run,
        start_time=record_start,
        spec_config=config_spectrogram
    )


def delete_old_files(root_dir_path, days):
    files_list = os.listdir(root_dir_path)
    current_time = time.time()
    for file in files_list:
        file_path = os.path.join(root_dir_path, file)
        if os.path.isfile(file_path):
            if (current_time - os.stat(file_path).st_mtime) > days * 86400:
                logging.info(f"Deleting file '{file_path}'")
                os.remove(file_path)


def main():
    logging.basicConfig(format='%(asctime)s %(levelname)s - %(message)s', level=logging.INFO)
    logging.debug("Start of program")

    # Read configuration file. Use config.ini or config_dist.ini if it does not exist.
    config_file = Path('config.ini')
    if not config_file.exists():
        config_file = Path('config_dist.ini')

    # Get configuration
    config = configparser.RawConfigParser()
    config.read(config_file)

    config_schedule = config['schedule']
    config_schedule['config_time_sec'] = str(random.randint(20, 60))
    slot_length_min = config_schedule.getint('slot_length_min', fallback=10)
    pool = concurrent.futures.ThreadPoolExecutor()

    next_run = None
    next_run_compare = None
    logging.info("Entering loop")
    while True:
        current_time = datetime.now(timezone.utc)
        # Get a list of all minutes and step by slot_minute
        sched_minutes = range(0, 60, slot_length_min)
        sched_minutes = [current_time.replace(minute=x, second=0, microsecond=0) for x in sched_minutes]

        # Extend the list, so we can still pick a slot past the next hour.
        sched_minutes.extend([x + timedelta(hours=1) for x in sched_minutes])

        # Start config_time_sec early for configuring the browser.
        config_time_sec = config_schedule.getint('config_time_sec')
        sched_with_config = [x - timedelta(seconds=config_time_sec) for x in sched_minutes]

        # Find next possible slot.
        if next_run is None:
            for date in sched_with_config:
                if current_time < date:
                    # We found a next run slot.
                    next_run = date
                    break

        # Save next_run in next_run_compare
        if next_run_compare is None and next_run is not None:
            next_run_compare = next_run

        # Reset if next_run if different from next_run_compare
        if next_run_compare != next_run:
            next_run_compare = None

        # Reset if we are past the scheduled run.
        if current_time > next_run:
            next_run = None

        # Set up and configure scheduler
        if next_run:
            logging.info(f"Scheduling next session at: {next_run}")
            s = sched.scheduler(time.time, time.sleep)
            s.enterabs(next_run.timestamp(), 0, spawn_rec_and_process, argument=(pool, config, next_run))
            s.run()

        time.sleep(1)


if __name__ == "__main__":
    main()
