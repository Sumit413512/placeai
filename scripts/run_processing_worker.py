"""Dedicated Render worker entry points; no public HTTP server or new queue broker."""
import argparse
import logging
from pathlib import Path
import signal
import sys
from threading import Event, Thread
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kind', choices=['assessments', 'learning'], required=True)
    args = parser.parse_args()
    stop = Event()
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: stop.set())
    if args.kind == 'assessments':
        from app.assessment_worker import run
        targets = [run]
    else:
        from app.learning_worker import run as notes
        from app.learning_video_worker import run as videos
        targets = [notes, videos]
    threads = [Thread(target=target, args=(stop,), daemon=True, name=target.__module__)
               for target in targets]
    for thread in threads:
        thread.start()
    while not stop.wait(1):
        if any(not thread.is_alive() for thread in threads):
            stop.set()
            raise RuntimeError('Processing loop stopped unexpectedly')
    # Durable per-stage leases/checkpoints survive a platform-enforced shutdown.
    deadline = time.monotonic() + 25
    for thread in threads:
        thread.join(timeout=max(0, deadline-time.monotonic()))


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
