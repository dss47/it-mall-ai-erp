import os
import shutil
import socket
import threading
import time

from . import db
from .config import LISTEN_HOST, LISTEN_PORT, SESS_DIR
from .log import log
from .session import CallSession
from .tts import ensure_tts


def purge_old_sessions(max_age_days=7):
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        for name in os.listdir(SESS_DIR):
            p = os.path.join(SESS_DIR, name)
            try:
                if os.path.isdir(p) and os.path.getmtime(p) < cutoff:
                    shutil.rmtree(p, ignore_errors=True)
                    removed += 1
            except Exception:
                pass
    except Exception:
        pass
    if removed:
        log("purged %d old session dirs" % removed)


def handle_connection(conn):
    conn.settimeout(5.0)
    try:
        header = b""
        while len(header) < 19:
            part = conn.recv(19 - len(header))
            if not part:
                return
            header += part
    except Exception:
        return
    if len(header) < 19 or header[0] != 0x01:
        return
    uuid_hex = header[3:19].hex()
    uuid_str = "%s-%s-%s-%s-%s" % (uuid_hex[0:8], uuid_hex[8:12], uuid_hex[12:16],
                                   uuid_hex[16:20], uuid_hex[20:32])
    conn.settimeout(None)
    sess = CallSession(conn, uuid_str)
    t = threading.Thread(target=sess.reader, daemon=True)
    t.start()
    sess.run()


def _periodic_purge(interval_s=86400):
    """Background thread: purge old sessions every `interval_s` seconds."""
    while True:
        time.sleep(interval_s)
        purge_old_sessions()


def main():
    ensure_tts()
    db.init_db()
    purge_old_sessions()
    threading.Thread(target=_periodic_purge, daemon=True).start()
    # NOTE: pdf_service runs as a dedicated systemd service (pdf-quote-service)
    # on port 8301 (127.0.0.1 only). Do NOT spawn it here to avoid port conflict.
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((LISTEN_HOST, LISTEN_PORT))
    srv.listen(16)
    log("agent_server listening on %s:%d" % (LISTEN_HOST, LISTEN_PORT))
    while True:
        try:
            conn, _ = srv.accept()
        except Exception:
            continue
        threading.Thread(target=handle_connection, args=(conn,), daemon=True).start()


if __name__ == "__main__":
    main()
