import time

from .config import LOG


def log(msg):
    line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        with open(LOG, "a") as f:
            f.write(line)
    except Exception:
        pass
