import os
import random
import re
import socket
import struct
import threading
import time
from collections import deque

import numpy as np

from . import db, engine, llm
from .audio import rms, slin_to_wav
from .config import (BARG_IN_FRAMES, BARG_PROB, ENERGY_MIN, EXPECTATIONS,
                     MAX_SPEECH_TURNS, MIN_UTTERANCE_S, POST_TTS_HOLD,
                     SAMPLE_RATE, SESS_DIR, SILENCE_HANGUP_S, SPEECH_PROB,
                     VAD_FRAME)
from .extract import extract_name, extract_phone_digits, has_non_latin_letters
from .filters import (REG_AFFIRM, REG_GOODBYE, REG_NEGATE, is_filler_word,
                      is_noise, is_trivial_motif)
from .log import log
from .prompt import OPENING_GREETING
from .registry import QUESTION_STEPS, Registry
from .stt import groq_stt
from .tts import ensure_tts, piper_tts
from .vad import SileroVAD


def _gen_reference():
    return "R-%04d" % random.randint(0, 9999)


class CallSession:
    def __init__(self, sock, uuid_hex):
        self.sock = sock
        try:
            self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except Exception:
            pass

        self.uuid = uuid_hex
        self.sess_dir = os.path.join(SESS_DIR, uuid_hex)
        os.makedirs(self.sess_dir, exist_ok=True)
        self.history = []
        self.reference = _gen_reference()
        self.turns = 0
        self.alive = True
        self.call_id = None
        self.closed_bye = False
        self.demande_saved = False
        self.caller_partner = None
        self.caller_phone = None

        self.lock = threading.Lock()
        self.send_lock = threading.Lock()
        self.utterances = deque()
        self.event = threading.Event()
        self.playing = False
        self.vad_hold_until = 0.0
        self.barge_in = threading.Event()
        self.barg_frames = 0
        self.last_text = ""
        self.ignored_count = 0

        self.registry = Registry()
        self.patience_s = EXPECTATIONS["free"]["patience"]
        self.max_utter_s = EXPECTATIONS["free"]["max_utter"]

        self.vad = SileroVAD()
        self.pcm_buf = b""
        self.speaking = False
        self.silent_frames = 0
        self.cur = bytearray()
        self.cur_start = 0.0
        self.preroll = deque(maxlen=8)

        with open(os.path.join(self.sess_dir, "history.json"), "w") as f:
            import json
            json.dump([], f)

    def _update_patience(self):
        exp = EXPECTATIONS.get(self.registry.expectation(), EXPECTATIONS["free"])
        self.patience_s = exp["patience"]
        self.max_utter_s = exp["max_utter"]

    def reader(self):
        buf = b""
        while self.alive:
            try:
                chunk = self.sock.recv(4096)
            except Exception:
                break
            if not chunk:
                break
            buf += chunk
            while len(buf) >= 3:
                kind = buf[0]
                if kind == 0x00:
                    self.alive = False
                    self.event.set()
                    return
                if kind != 0x10:
                    buf = buf[1:]
                    continue
                length = (buf[1] << 8) | buf[2]
                if len(buf) < 3 + length:
                    break
                pcm = buf[3:3 + length]
                buf = buf[3 + length:]
                self.feed(pcm)
        self.alive = False
        self.event.set()

    def feed(self, pcm):
        if time.time() < self.vad_hold_until:
            self.pcm_buf = b""
            return
        self.pcm_buf += pcm
        if self.playing:
            self._barge_detect()
            return
        self._process_buffered()

    def _barge_detect(self):
        if self.barge_in.is_set():
            return
        frame_bytes = VAD_FRAME * 2
        while len(self.pcm_buf) >= frame_bytes:
            frame = np.frombuffer(self.pcm_buf[:frame_bytes], dtype=np.int16)
            self.pcm_buf = self.pcm_buf[frame_bytes:]
            if rms(frame) < ENERGY_MIN:
                continue
            prob = self.vad.prob(frame)
            if prob > BARG_PROB:
                self.barg_frames += 1
                if self.barg_frames >= BARG_IN_FRAMES:
                    self.barge_in.set()
                    self.barg_frames = 0
                    return
            else:
                self.barg_frames = 0

    def _process_buffered(self):
        frame_bytes = VAD_FRAME * 2
        while len(self.pcm_buf) >= frame_bytes:
            frame = np.frombuffer(self.pcm_buf[:frame_bytes], dtype=np.int16)
            self.pcm_buf = self.pcm_buf[frame_bytes:]
            self.process_frame(frame)

    def process_frame(self, frame):
        prob = self.vad.prob(frame)
        if rms(frame) < ENERGY_MIN:
            prob = 0.0
        if prob > SPEECH_PROB:
            self.silent_frames = 0
            if not self.speaking:
                self.speaking = True
                self.cur = bytearray(b"".join(self.preroll))
                self.cur_start = time.time()
            elif (time.time() - self.cur_start) > self.max_utter_s:
                self.finish_utterance()
                return
        else:
            if self.speaking:
                self.silent_frames += 1
                end_silence = int(self.patience_s * SAMPLE_RATE / VAD_FRAME)
                if self.silent_frames >= end_silence:
                    self.finish_utterance()
                    return
                if (time.time() - self.cur_start) > self.max_utter_s:
                    self.finish_utterance()
                    return
        if self.speaking:
            self.cur += frame.tobytes()
        self.preroll.append(frame.tobytes())

    def finish_utterance(self):
        audio = bytes(self.cur)
        self.speaking = False
        self.silent_frames = 0
        self.cur = bytearray()
        self.vad.reset()
        if len(audio) >= MIN_UTTERANCE_S * SAMPLE_RATE * 2:
            with self.lock:
                self.utterances.append(audio)
            self.event.set()

    def next_utterance(self, timeout):
        deadline = time.time() + timeout
        while self.alive:
            remaining = deadline - time.time()
            if remaining <= 0:
                return None
            self.event.wait(min(remaining, 1.0))
            if not self.alive:
                return None
            with self.lock:
                if self.utterances:
                    self.event.clear()
                    return self.utterances.popleft()
        return None

    def send_frame(self, pcm):
        if isinstance(pcm, np.ndarray):
            pcm = pcm.tobytes()
        payload = b"\x10" + struct.pack(">H", len(pcm)) + pcm
        with self.send_lock:
            self.sock.sendall(payload)

    def send_silence(self, nbytes=320):
        payload = b"\x10" + struct.pack(">H", nbytes) + (b"\x00" * nbytes)
        try:
            with self.send_lock:
                self.sock.sendall(payload)
        except Exception:
            pass

    def _keepalive(self):
        chunk = 320
        while self.alive:
            if not self.playing:
                self.send_silence(chunk)
            time.sleep(0.02)

    def play(self, pcm, final=False):
        if isinstance(pcm, np.ndarray):
            pcm = pcm.tobytes()

        self.playing = True
        self.barge_in.clear()
        self.barg_frames = 0
        interrupted = False

        chunk_size = 320
        frame_duration = 0.020
        total_chunks = len(pcm) // chunk_size

        start_time = time.monotonic()
        try:
            for idx in range(total_chunks):
                if not self.alive or self.barge_in.is_set():
                    interrupted = True
                    break

                frame = pcm[idx * chunk_size : (idx + 1) * chunk_size]
                try:
                    self.send_frame(frame)
                except Exception:
                    return

                next_target = start_time + ((idx + 1) * frame_duration)
                sleep_time = next_target - time.monotonic()
                if sleep_time > 0:
                    time.sleep(sleep_time)

            if final and not interrupted:
                for _ in range(50):
                    if not self.alive or self.barge_in.is_set():
                        break
                    self.send_silence(chunk_size)
                    time.sleep(0.02)
        finally:
            self.playing = False
            self.vad_hold_until = time.time() + (0.15 if interrupted else POST_TTS_HOLD)

    def end(self):
        try:
            with self.send_lock:
                self.sock.sendall(b"\x00")
        except Exception:
            pass
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            self.sock.close()
        except Exception:
            pass

    def handle_turn(self, turn, audio):
        np_audio = np.frombuffer(audio, dtype=np.int16)
        wav8 = slin_to_wav(np_audio, SAMPLE_RATE)
        with open(os.path.join(self.sess_dir, "turn%d.wav" % turn), "wb") as f:
            f.write(wav8)

        text = groq_stt(np_audio)
        log("stt turn=%d at %.3f: %s" % (turn, time.time(), text))
        if not text:
            log("empty stt turn=%d" % turn)
            return

        if is_noise(text):
            log("ignored noise turn=%d: %r" % (turn, text))
            return

        step = self.registry.step
        low = text.strip().strip(".").strip().lower()
        gated = False
        if step in QUESTION_STEPS:
            informative = bool(extract_name(text) or extract_phone_digits(text)
                               or has_non_latin_letters(text)
                               or REG_AFFIRM.search(text) or REG_NEGATE.search(text)
                               or REG_GOODBYE.search(text))
            gated = not informative and is_trivial_motif(text)
        elif is_filler_word(text) and low == self.last_text:
            gated = True

        if gated:
            self.ignored_count += 1
            if self.ignored_count >= 2:
                self.ignored_count = 0
                reply = llm.directive(self, text,
                                      "Le client n'a rien dit de neuf. Relance-le gentiment "
                                      "pour obtenir sa réponse à la question en cours.")
                if reply is not None:
                    self._speak(turn, reply, text, nudge=True)
            else:
                log("ignored filler turn=%d: %r" % (turn, text))
            return

        self.ignored_count = 0
        self.last_text = low if len(text) < 30 else ""

        reply = engine.process_turn(self, text)
        log("llm turn=%d at %.3f: %s" % (turn, time.time(),
                                         __import__("json").dumps(reply, ensure_ascii=False)[:300]))
        if reply is None:
            reply = {"reply_text": "Je n'ai pas bien entendu. Pourriez-vous répéter, s'il vous plaît ?",
                     "analysis": {}}
        self._speak(turn, reply, text)

    def _speak(self, turn, reply, text, nudge=False):
        reply_text = (reply.get("reply_text") or "").strip()
        end_call = bool(reply.get("end_call"))

        db.log_turn(self.call_id, "user", text)
        if reply_text:
            self.history.append({"role": "user", "content": " " + text})
            self.history.append({"role": "assistant", "content": " " + reply_text})
            db.log_turn(self.call_id, "assistant", reply_text)
        with open(os.path.join(self.sess_dir, "history.json"), "w") as f:
            import json
            json.dump(self.history, f, ensure_ascii=False)

        if reply_text:
            ensure_tts()
            slin8 = piper_tts(reply_text)
            if slin8 is None:
                log("tts silence turn=%d" % turn)
                return
            with open(os.path.join(self.sess_dir, "reply%d.wav" % turn), "wb") as f:
                f.write(slin_to_wav(slin8, SAMPLE_RATE))
            final = bool(end_call)
            self.play(slin8, final=final)
            log("tts turn=%d played at %.3f%s" % (turn, time.time(), " (nudge)" if nudge else ""))

        if end_call:
            log("ending call turn=%d (end_call)" % turn)
            self.closed_bye = True
            self.alive = False
            self.event.set()

    def run(self):
        log("audiosocket call start %s at %.3f" % (self.uuid, time.time()))
        self.call_id = db.create_call(self.uuid, self.sess_dir, self.reference)

        self.caller_phone = db.read_caller_phone(self.uuid)
        self.caller_partner = None
        greeting = OPENING_GREETING
        if self.caller_phone:
            self.registry.state["phone"] = self.caller_phone
            self.caller_partner = db.lookup_client(self.caller_phone)
            if self.caller_partner:
                pname = self.caller_partner.get("name") or ""
                if pname:
                    self.registry.state["name"] = pname
                    self.registry.state["done"] = True
                    first_name = pname.split()[0]
                    greeting = (
                        f"Bonjour {first_name}, ravi de vous réentendre chez IT Mall. "
                        f"Comment puis-je vous aider aujourd'hui ?"
                    )
                    log("known caller: %s (%s) -> greeting %s" % (pname, self.caller_phone, first_name))

        threading.Thread(target=self._keepalive, daemon=True).start()
        try:
            self.play_opening(greeting)
            self.history = [{"role": "assistant", "content": " " + greeting}]
            if self.caller_partner:
                pname = self.caller_partner.get("name") or ""
                first_name = pname.split()[0] if pname else ""
                pcomp = self.caller_partner.get("company_name") or ""
                ctx = ("Contexte client : tu parles à %s%s. "
                       "Tu le connais déjà, ne redemande pas ses coordonnées."
                       % (first_name, (", %s" % pcomp) if pcomp else ""))
                self.history.append({"role": "user", "content": " " + ctx})
            db.log_turn(self.call_id, "assistant", greeting)
            while self.alive and self.turns < MAX_SPEECH_TURNS:
                self._update_patience()
                audio = self.next_utterance(SILENCE_HANGUP_S)
                if audio is None or not self.alive:
                    break
                self.turns += 1
                turn = self.turns
                log("payload turn=%d at %.3f" % (turn, time.time()))
                self.handle_turn(turn, audio)
                self._update_patience()
            if self.alive and self.history and self.history[-1].get("role") == "assistant":
                reply = piper_tts("Je vous remercie de votre appel. Bonne journée et à bientôt.")
                if reply is not None:
                    self.play(reply, final=True)
        finally:
            # Raccrocher immédiatement la ligne téléphonique côté Asterisk
            self.alive = False
            self.event.set()
            self.end()
            log("audiosocket socket closed for %s" % self.uuid)

            self._save_missing_demande()
            db.end_call(self.call_id, "completed" if self.closed_bye else "ended")

            st = self.registry.state
            partner_name = self.caller_partner.get("name") if self.caller_partner else None
            caller_name = partner_name or st.get("name")
            caller_phone = st.get("phone") or self.caller_phone or (
                self.caller_partner.get("phone") if self.caller_partner else None)
            partner_id = self.caller_partner.get("id") if self.caller_partner else None
            if not partner_id and caller_phone:
                p = db.lookup_client(caller_phone)
                if p:
                    partner_id = p.get("id")

            # Synthèse globale post-appel pour extraction multi-produits précise (en tâche de fond pour ne pas bloquer)
            try:
                post_summary = llm.post_call_analyze(self.history, caller_name=caller_name or "Client")
                if post_summary and isinstance(post_summary, dict):
                    if post_summary.get("intent_type"):
                        st["intent_type"] = post_summary["intent_type"]
                    if post_summary.get("category"):
                        st["category"] = post_summary["category"]
                    if post_summary.get("motif"):
                        st["motif"] = post_summary["motif"]
                    if post_summary.get("items") and isinstance(post_summary["items"], list):
                        st["items"] = post_summary["items"]
                    if post_summary.get("estimated_total_revenue") is not None:
                        try:
                            st["estimated_total_revenue"] = float(post_summary["estimated_total_revenue"])
                        except Exception:
                            pass
                    if post_summary.get("urgency"):
                        st["urgency"] = post_summary["urgency"]
                    if post_summary.get("needs_human"):
                        st["needs_human"] = True
                    log("post_call_analyze completed: motif=%r intent=%r items=%d rev=%s" % (
                        st.get("motif"), st.get("intent_type"), len(st.get("items", [])), st.get("estimated_total_revenue")))
            except Exception as e:
                log("post_call_analyze error: %r" % e)

            motif = (st.get("motif") or "").strip()
            # Auto-detect call state for Odoo (urgent, to_call, done)
            is_urgent = False
            urgency = (st.get("urgency") or "").lower()
            needs_human = bool(st.get("needs_human") or st.get("human_requested"))
            low_motif = (motif or "").lower()

            # 1. Urgent: Panne, coupure, réclamation critique (avec gestion de la négation)
            is_negated_urgent = any(neg in low_motif for neg in ("non urgent", "pas urgent", "sans urgence", "non critique", "aucune urgence", "pas d'urgence"))
            if not is_negated_urgent:
                for kw in ("panne", "bloqu", "coupure", "urgence", "urgent", "reclamation", "réclamation", "hs", "critique", "ne marche pas", "ne fonctionne pas"):
                    if re.search(r"\b" + kw, low_motif):
                        is_urgent = True
                        break
                if urgency in ("high", "haute", "urgent", "urgente", "critique"):
                    is_urgent = True

            # 2. To Call (À rappeler): Uniquement si une action humaine est requise (rappel demandé, devis, commande à valider)
            requires_followup = False
            if needs_human or st.get("human_requested"):
                requires_followup = True
            for kw in ("rappel", "rappeler", "devis", "commande", "commander", "achat", "rdv", "rendez-vous"):
                if kw in low_motif:
                    requires_followup = True
                    break

            # Si l'appel était un renseignement, une confirmation, une erreur ou si le client n'a rien demandé d'autre -> Traité (done)
            if any(kw in low_motif for kw in ("erreur", "tromp", "faux num", "mauvais num", "rien", "information", "renseignement", "vérification", "confirmation", "disponibilité")):
                requires_followup = False

            call_state = "done"
            if is_urgent:
                call_state = "urgent"
            elif requires_followup:
                call_state = "to_call"
            # Auto-assign department role for Odoo (support, stock/livraison, account/paiement, sales/commercial)
            category = (st.get("category") or "").lower()
            intent = (st.get("intent_type") or "").lower()
            
            is_delivery_stock = (
                category in ("livraison", "stock", "expedition") or
                intent == "order_cancellation" or
                any(kw in low_motif for kw in ("livraison", "livrer", "stock", "colis", "expedition", "expédition", "transporteur", "reception", "réception", "suivi"))
            )
            is_accounting = (
                category in ("paiement", "facturation", "comptabilite") or
                any(kw in low_motif for kw in ("facture", "paiement", "payer", "virement", "reglement", "règlement", "solde"))
            )

            if is_urgent:
                target_role = "support"
            elif is_delivery_stock:
                target_role = "stock"
            elif is_accounting:
                target_role = "account"
            else:
                target_role = "sales"
            log_id = db.save_call_log(
                caller_name=caller_name,
                caller_phone=caller_phone,
                motif=motif or "Inconnu",
                state=call_state,
                target_role=target_role,
                partner_id=partner_id,
                notes="Appel traité par IA. Réf: %s" % (self.reference or ""),
                call_uuid=self.uuid,
            )

            # Attach audio recording from Session
            def _async_attach_audio(uuid, call_id):
                import time, glob, os, base64, subprocess, psycopg2
                sess_dir = getattr(self, "sess_dir", f"/opt/voice-agent/sessions/{uuid}")
                mp3_path = os.path.join(sess_dir, "conversation.mp3")
                
                # Check for existing recordings in /opt/voice-agent/recordings or merge session turns
                recordings = glob.glob(f"/opt/voice-agent/recordings/*_{uuid[:8]}.mp3")
                if recordings:
                    mp3_path = recordings[0]
                elif os.path.isdir(sess_dir):
                    # Gather and sort all turn WAV files (caller speech AND AI agent replies)
                    turns = glob.glob(os.path.join(sess_dir, "turn*.wav"))
                    wav_files = []
                    # Interleave turns and replies chronologically: turn1 -> reply1 -> turn2 -> reply2
                    for i in range(1, len(turns) + 5):
                        t_file = os.path.join(sess_dir, f"turn{i}.wav")
                        r_file = os.path.join(sess_dir, f"reply{i}.wav")
                        if os.path.exists(t_file) and os.path.getsize(t_file) > 44:
                            wav_files.append(t_file)
                        if os.path.exists(r_file) and os.path.getsize(r_file) > 44:
                            wav_files.append(r_file)

                    if wav_files:
                        try:
                            # Create concat list for ffmpeg
                            list_file = os.path.join(sess_dir, "turns.txt")
                            with open(list_file, "w") as lf:
                                for wf in wav_files:
                                    lf.write(f"file '{wf}'\n")
                            subprocess.run([
                                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                                "-i", list_file, "-c:a", "libmp3lame", "-b:a", "64k", mp3_path
                            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
                        except Exception as e:
                            log("ffmpeg merge error: %r" % e)

                if os.path.exists(mp3_path):
                    try:
                        with open(mp3_path, "rb") as f:
                            data = f.read()
                        if len(data) > 100:
                            b64_data = base64.b64encode(data).decode('utf-8')
                            con = db._odoo_conn()
                            cur = con.cursor()
                            cur.execute("UPDATE it_mall_call_log SET recording_filename = 'enregistrement.mp3' WHERE id = %s", (call_id,))
                            cur.execute("DELETE FROM ir_attachment WHERE res_model = 'it_mall.call.log' AND res_id = %s AND res_field = 'recording_file'", (call_id,))
                            cur.execute("""
                                INSERT INTO ir_attachment (name, res_model, res_id, res_field, type, db_datas, mimetype, file_size, public, create_date, write_date)
                                VALUES ('enregistrement.mp3', 'it_mall.call.log', %s, 'recording_file', 'binary', %s, 'audio/mpeg', %s, true, NOW(), NOW())
                            """, (call_id, psycopg2.Binary(data), len(data)))
                            con.commit()
                            con.close()
                            log("Attached audio %s (%d bytes) to call log #%d" % (mp3_path, len(data), call_id))
                    except Exception as e:
                        log("Error attaching audio: %r" % e)

            # Attach audio recording directly and reliably before closing session
            if log_id:
                try:
                    _async_attach_audio(self.uuid, log_id)
                except Exception as e:
                    log("Error attaching audio: %r" % e)

            # Trigger n8n Webhook for post-call workflows (CRM leads, WhatsApp, alerts)
            import urllib.request
            import json
            def send_n8n():
                import time
                transcript_text = "\n".join([f"{h.get('role', 'user')}: {h.get('content', '').strip()}" for h in getattr(self, "history", []) if h.get("content")])
                payload = {
                    "reference": self.reference,
                    "caller_name": caller_name,
                    "caller_phone": caller_phone,
                    "motif": motif,
                    "call_state": call_state,
                    "intent_type": st.get("intent_type") or ("support_urgent" if is_urgent else "general_inquiry"),
                    "category": st.get("category"),
                    "desired_outcome": st.get("desired_outcome"),
                    "needs_human": st.get("needs_human"),
                    "partner_id": partner_id,
                    "expected_revenue": st.get("estimated_total_revenue", 0),
                    "items": st.get("items", []),
                    "transcript": transcript_text,
                    "call_uuid": self.uuid
                }
                data_bytes = json.dumps(payload).encode('utf-8')
                urls = ('http://127.0.0.1:5678/webhook/hotline', 'http://127.0.0.1:5678/webhook-test/hotline')
                
                # Retry up to 3 times with exponential backoff (1s, 3s, 6s)
                delivered = False
                for attempt in range(1, 4):
                    for url in urls:
                        try:
                            req = urllib.request.Request(
                                url,
                                data=data_bytes,
                                headers={'Content-Type': 'application/json'},
                                method='POST'
                            )
                            with urllib.request.urlopen(req, timeout=10) as resp:
                                if resp.status in (200, 201):
                                    log("n8n webhook triggered -> status %d (attempt %d)" % (resp.status, attempt))
                                    delivered = True
                                    break
                        except Exception as e:
                            log("n8n webhook attempt %d error for %s: %r" % (attempt, url, e))
                    if delivered:
                        break
                    time.sleep(attempt * 2.0)
            threading.Thread(target=send_n8n, daemon=True).start()

            self.end()
            self.alive = False
            self.event.set()
            log("audiosocket call end %s" % self.uuid)

    def _save_missing_demande(self):
        if self.demande_saved:
            return
        st = self.registry.state
        motif = (st.get("motif") or "").strip()
        if not motif:
            return
        db.save_demande(self.call_id, None, self.reference or "R-0000", motif[:300],
                        category=st.get("category"),
                        desired_outcome=st.get("desired_outcome"),
                        urgency=st.get("urgency"),
                        sentiment=st.get("sentiment"),
                        needs_human=bool(st.get("needs_human")))
        log("motif saved (no registration): %r" % motif[:120])

    def play_opening(self, greeting=None):
        try:
            chunk = 320
            for _ in range(50):
                if not self.alive:
                    return
                self.send_silence(chunk)
                time.sleep(0.02)
            text = greeting or OPENING_GREETING
            audio = piper_tts(text)
            if audio is not None:
                self.play(audio)
        except Exception as e:
            log("opening error: %r" % e)
