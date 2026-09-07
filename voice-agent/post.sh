#!/bin/bash
BASE="$1"
LOG=/var/log/asterisk/ai_agent.log
REC_DIR=/opt/voice-agent/recordings
KEEP_DAYS=30

echo "=== post $(date) base=$BASE ===" >>"$LOG"

if [ -f "$BASE.processed" ]; then
    echo "already processed, skip" >>"$LOG"
    exit 0
fi
if [ ! -f "$BASE.ulaw" ]; then
    echo "no ulaw for $BASE" >>"$LOG"
    exit 1
fi

mkdir -p "$REC_DIR"
UUID=$(basename "$BASE")
TS=$(date +%Y-%m-%d_%H%M%S)
MP3="$REC_DIR/${TS}_${UUID:0:8}.mp3"

sox -t raw -r 8000 -c 1 -e mu-law "$BASE.ulaw" -r 22050 "$BASE.wav" >>"$LOG" 2>&1
if [ ! -f "$BASE.wav" ]; then
    echo "no wav produced" >>"$LOG"
    exit 1
fi

lame -q 5 -b 64 "$BASE.wav" "$MP3" >>"$LOG" 2>&1
if [ ! -f "$MP3" ]; then
    echo "no mp3 produced" >>"$LOG"
    exit 1
fi

rm -f "$BASE.ulaw" "$BASE.wav"
touch "$BASE.processed"
echo "mp3 saved: $MP3" >>"$LOG"

# Upload to Odoo via psycopg2
python3 -c "
import psycopg2, os, hashlib

uuid = '$UUID'
mp3_path = '$MP3'
fname = 'appel_' + uuid[:8] + '.mp3'

try:
    with open(mp3_path, 'rb') as f:
        data = f.read()

    conn = psycopg2.connect(
        dbname=os.environ.get('ODOO_DB', 'it_mall_db'),
        user=os.environ.get('ODOO_USER', 'odoo'),
        password=os.environ.get('ODOO_PASS', 'odoo'),
        host=os.environ.get('ODOO_HOST', 'localhost'),
        port=int(os.environ.get('ODOO_PORT', 5432))
    )
    cur = conn.cursor()

    # Find the call log record
    cur.execute('SELECT id FROM it_mall_call_log WHERE call_uuid = %s LIMIT 1', (uuid,))
    row = cur.fetchone()
    if not row:
        cur.execute('SELECT id FROM it_mall_call_log ORDER BY id DESC LIMIT 1')
        row = cur.fetchone()
    if not row:
        print('No call log found for uuid %s' % uuid)
        conn.close()
        exit(0)

    log_id = row[0]
    checksum = hashlib.md5(data).hexdigest()

    # Insert attachment
    cur.execute('''
        INSERT INTO ir_attachment (name, res_model, res_id, res_field, type, db_datas,
                                   mimetype, file_size, checksum, create_date, write_date)
        VALUES (%s, 'it_mall.call.log', %s, 'recording_file', 'binary', %s,
                'audio/mpeg', %s, %s, NOW(), NOW())
        RETURNING id
    ''', (fname, log_id, psycopg2.Binary(data), len(data), checksum))
    att_id = cur.fetchone()[0]

    # Update call log with filename
    cur.execute('UPDATE it_mall_call_log SET recording_filename = %s, write_date = NOW() WHERE id = %s',
                (fname, log_id))
    conn.commit()
    print('Uploaded audio to Odoo: attachment %d for call_log %d' % (att_id, log_id))
    conn.close()
except Exception as e:
    print('Failed to upload audio to Odoo: %s' % e)
" >>"$LOG" 2>&1

find "$REC_DIR" -maxdepth 1 -name '*.mp3' -mtime +"$KEEP_DAYS" -delete >>"$LOG" 2>&1
echo "done" >>"$LOG"
