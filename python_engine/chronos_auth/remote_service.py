"""Secure Remote Alerts, Notifications, and Remote Lock Commands.

Opt-in remote services layer using strictly standard library:
- Telegram Bot Notifications & Remote Command Poller (/lock, /status, /snooze)
- SMTP / Email Alerts (TLS/SSL supported)
- Anti-spam cooldown rate limiting
- 100% Free, local, zero paid APIs, zero third-party dependencies.
"""

from __future__ import annotations

import email.encoders
import json
import os
import smtplib
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import threading
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from chronos_auth.runtime_config import (
    CredentialsStore,
    SecurityPolicyStore,
    REMOTE_RELOAD_PATH,
    LIVE_STATE_PATH,
    LEGACY_LIVE_STATE_PATH,
    read_json,
    get_lock_mode,
)
from chronos_auth.system_actions import lock_workstation, capture_webcam_snapshot


# =============================================================================
# TELEGRAM BOT CLIENT (STANDARD LIBRARY)
# =============================================================================
class TelegramClient:
    """Lightweight Telegram Bot API client using standard library urllib."""

    BASE_URL = "https://api.telegram.org/bot"

    @classmethod
    def send_message(
        cls,
        token: str,
        chat_id: str,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Sends a text message via Telegram Bot API with optional inline keyboard markup."""
        if not token or not chat_id:
            return False, "Telegram token or chat_id is missing."

        url = f"{cls.BASE_URL}{token.strip()}/sendMessage"
        payload_dict: Dict[str, Any] = {
            "chat_id": str(chat_id).strip(),
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload_dict["reply_markup"] = reply_markup

        payload = json.dumps(payload_dict).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return True, "Message delivered successfully."
                return False, data.get("description", "Unknown Telegram error.")
        except urllib.error.HTTPError as e:
            try:
                err_data = json.loads(e.read().decode("utf-8"))
                return False, err_data.get("description", f"HTTP error {e.code}")
            except Exception:
                return False, f"Telegram HTTP error: {e.code} {e.reason}"
        except Exception as exc:
            return False, f"Telegram connection error: {exc}"

    @classmethod
    def answer_callback_query(cls, token: str, callback_query_id: str, text: str = "") -> bool:
        """Acknowledges inline keyboard callback button press on Telegram."""
        if not token or not callback_query_id:
            return False
        url = f"{cls.BASE_URL}{token.strip()}/answerCallbackQuery"
        payload = json.dumps({
            "callback_query_id": str(callback_query_id).strip(),
            "text": text,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=8.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return bool(data.get("ok"))
        except Exception:
            return False

    @classmethod
    def send_photo(cls, token: str, chat_id: str, photo_path: Path, caption: str = "") -> Tuple[bool, str]:
        """Sends a photo via multipart/form-data."""
        if not token or not chat_id or not photo_path.exists():
            return False, "Photo file or Telegram credentials missing."

        url = f"{cls.BASE_URL}{token.strip()}/sendPhoto"
        boundary = f"----ChronosBoundary{int(time.time() * 1000)}"

        try:
            photo_bytes = photo_path.read_bytes()
        except OSError as e:
            return False, f"Could not read snapshot photo: {e}"

        body = bytearray()
        # Field: chat_id
        body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode())
        # Field: caption
        if caption:
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode())
            body.extend(f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nMarkdown\r\n".encode())
        # Field: photo file
        body.extend(
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"photo\"; filename=\"snapshot.jpg\"\r\n"
            f"Content-Type: image/jpeg\r\n\r\n".encode()
        )
        body.extend(photo_bytes)
        body.extend(f"\r\n--{boundary}--\r\n".encode())

        req = urllib.request.Request(
            url,
            data=bytes(body),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=18.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return True, "Snapshot photo delivered successfully."
                return False, data.get("description", "Failed to upload photo.")
        except Exception as exc:
            return False, f"Telegram photo upload error: {exc}"

    @classmethod
    def get_updates(cls, token: str, offset: int = 0, timeout: int = 5) -> Tuple[bool, List[Dict[str, Any]]]:
        """Polls for incoming Telegram updates."""
        if not token:
            return False, []
        url = f"{cls.BASE_URL}{token.strip()}/getUpdates?offset={offset}&timeout={timeout}"
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout + 5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("ok"):
                    return True, data.get("result", [])
                return False, []
        except Exception:
            return False, []


# =============================================================================
# EMAIL / SMTP CLIENT (STANDARD LIBRARY)
# =============================================================================
class EmailClient:
    """Lightweight SMTP client supporting TLS and SSL."""

    @classmethod
    def send_email(
        cls,
        smtp_cfg: Dict[str, Any],
        subject: str,
        body_text: str,
        attachment_path: Optional[Path] = None,
    ) -> Tuple[bool, str]:
        """Sends an email alert via SMTP with optional image attachment."""
        host = smtp_cfg.get("host", "").strip()
        port = int(smtp_cfg.get("port", 587))
        user = smtp_cfg.get("user", "").strip()
        password = smtp_cfg.get("password", "").strip()
        recipient = smtp_cfg.get("recipient", "").strip()
        sender = smtp_cfg.get("sender", user).strip() or user
        use_ssl = bool(smtp_cfg.get("use_ssl", port == 465))
        use_tls = bool(smtp_cfg.get("use_tls", True))

        if not host or not recipient:
            return False, "SMTP host or recipient address is missing."

        msg = MIMEMultipart()
        msg["From"] = sender
        msg["To"] = recipient
        msg["Subject"] = subject
        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        if attachment_path and attachment_path.exists():
            try:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment_path.read_bytes())
                email.encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{attachment_path.name}"',
                )
                msg.attach(part)
            except Exception as e:
                pass

        try:
            ctx = ssl.create_default_context()
            if use_ssl:
                server = smtplib.SMTP_SSL(host, port, context=ctx, timeout=15.0)
            else:
                server = smtplib.SMTP(host, port, timeout=15.0)
                if use_tls:
                    server.starttls(context=ctx)

            if user and password:
                server.login(user, password)

            server.sendmail(sender, [recipient], msg.as_string())
            server.quit()
            return True, f"Email delivered to {recipient}."
        except smtplib.SMTPAuthenticationError:
            return False, "SMTP Authentication failed: check username/app password."
        except smtplib.SMTPConnectError:
            return False, f"Could not connect to SMTP server at {host}:{port}."
        except socket.timeout:
            return False, "SMTP connection timed out."
        except Exception as exc:
            return False, f"SMTP error: {exc}"


# =============================================================================
# REMOTE ALERT DISPATCHER & COMMAND POLLER
# =============================================================================
class RemoteAlertDispatcher:
    """
    Coordinates remote security alerts (Telegram / Email) and polls
    for authorized remote commands (e.g. /lock, /status, /snooze).
    """

    COOLDOWN_WARNING_SEC = 45.0    # 45 seconds between warning prompts (or if score drops further)
    COOLDOWN_LOCKOUT_SEC = 30.0    # 30 seconds for lockout alerts
    COOLDOWN_WALKAWAY_SEC = 120.0  # 2 minutes for walk-away alerts

    def __init__(
        self,
        credentials_store: Optional[CredentialsStore] = None,
        policy_store: Optional[SecurityPolicyStore] = None,
        live_state_path: Optional[Path] = None,
    ):
        self.credentials_store = credentials_store or CredentialsStore()
        self.policy_store = policy_store or SecurityPolicyStore()
        self.live_state_path = live_state_path or LIVE_STATE_PATH

        # Alert timestamps for rate limiting
        self.last_warning_at = 0.0
        self.last_warning_score = 100.0
        self.last_lockout_at = 0.0
        self.last_walkaway_at = 0.0

        # Background Telegram command poller state
        self._running = True
        self._last_update_offset = 0
        self._last_credentials_mtime = 0.0
        self.credentials = self.credentials_store.load()

        self._poller_thread: Optional[threading.Thread] = None
        self._start_poller()

    def _start_poller(self) -> None:
        """Starts background Telegram bot command polling thread."""
        self._poller_thread = threading.Thread(target=self._command_poller_loop, daemon=True)
        self._poller_thread.start()

    def stop(self) -> None:
        """Stops background threads."""
        self._running = False

    def reload_credentials(self) -> None:
        """Reloads credentials from disk."""
        self.credentials = self.credentials_store.load()

    def _check_credentials_reload(self) -> None:
        """Checks if credentials file was updated or reload requested."""
        if REMOTE_RELOAD_PATH.exists():
            try:
                REMOTE_RELOAD_PATH.unlink(missing_ok=True)
                self.reload_credentials()
            except OSError:
                pass

        try:
            mtime = self.credentials_store.path.stat().st_mtime
            if mtime > self._last_credentials_mtime:
                self._last_credentials_mtime = mtime
                self.reload_credentials()
        except OSError:
            pass

    # =========================================================================
    # ALERT DISPATCHING (WITH RATE LIMITING)
    # =========================================================================
    def notify_warning(
        self,
        trust_pct: float,
        threshold: float,
        impact_lines: List[str],
        instant_score: float = 0.0,
    ) -> None:
        """Dispatches an interactive alert asking user to verify identity when behavioral trust drops below threshold."""
        now = time.time()
        score_diff = self.last_warning_score - trust_pct

        # Rate-limiting: suppress if within cooldown, unless score dropped significantly further (>= 8%)
        if (now - self.last_warning_at < self.COOLDOWN_WARNING_SEC) and (score_diff < 8.0):
            return

        self.last_warning_at = now
        self.last_warning_score = trust_pct
        hostname = socket.gethostname()
        lock_mode = get_lock_mode()
        mode_str = "🛡️ Mode: *Simulation* (Automated lock is simulated)" if lock_mode == "simulate" else "🔒 Mode: *Enforcement* (Active Lockout)"

        bullet_points = "\n".join(f"• {line}" for line in impact_lines[:3]) if impact_lines else "• Uncharacteristic input rhythm detected"

        subject = f"⚠️ Chronos-Auth: Security Prompt on {hostname} ({trust_pct:.1f}%)"
        telegram_msg = (
            f"⚠️ *Security Verification: Low Trust ({trust_pct:.1f}%) on `{hostname}`*\n\n"
            f"{mode_str}\n"
            f"📉 *Cumulative Trust:* `{trust_pct:.1f}%` (Alert Threshold: `{threshold}%`)\n"
            f"⚡ *Instant Score:* `{instant_score:.1f}%`\n\n"
            f"❓ *Are you at your computer right now?*\n"
            f"• Tap *Yes, It's Me* or reply `yes` to give permission and continue typing even with a low score.\n"
            f"• Tap *Lock PC* or reply `lock` immediately if someone else is at your PC.\n\n"
            f"*Diagnostic Indicators:*\n{bullet_points}"
        )
        email_body = (
            f"Chronos-Auth Continuous Biometrics Security Prompt\n"
            f"===================================================\n\n"
            f"Machine Hostname : {hostname}\n"
            f"Operating Mode   : {lock_mode.upper()}\n"
            f"Cumulative Trust : {trust_pct:.1f}% (Warning Threshold: {threshold}%)\n"
            f"Instant Score    : {instant_score:.1f}%\n"
            f"Timestamp        : {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Is this you? If yes, reply 'yes' on Telegram to authorize and continue.\n"
            f"If not, lock your workstation immediately via Telegram bot (/lock).\n\n"
            f"Diagnostic Reasons:\n{bullet_points}\n"
        )

        telegram_buttons = {
            "inline_keyboard": [
                [
                    {"text": "✅ Yes, It's Me (Allow & Continue)", "callback_data": "allow"},
                    {"text": "🔒 Lock PC Now", "callback_data": "lock"},
                ],
                [
                    {"text": "⏸️ Snooze 1 Hour", "callback_data": "snooze_60"},
                    {"text": "📸 View Snapshot", "callback_data": "snapshot"},
                ]
            ]
        }

        self._dispatch_async(subject, telegram_msg, email_body, reply_markup=telegram_buttons)

    def notify_lockout(
        self,
        reason: str,
        impact_lines: List[str],
        capture_snapshot: bool = True,
    ) -> None:
        """Dispatches a high-priority alert when workstation lockout barrier is crossed."""
        now = time.time()
        if now - self.last_lockout_at < self.COOLDOWN_LOCKOUT_SEC:
            return

        self.last_lockout_at = now
        hostname = socket.gethostname()
        lock_mode = get_lock_mode()
        bullet_points = "\n".join(f"• {line}" for line in impact_lines[:4]) if impact_lines else f"• {reason}"

        snapshot_path: Optional[Path] = None
        if capture_snapshot:
            snapshot_path, _ = capture_webcam_snapshot()

        is_simulate = (lock_mode == "simulate")
        lock_headline = "🛡️ *LOCK SIMULATED (Simulation Mode Active)*" if is_simulate else "🔒 *WORKSTATION LOCKED*"
        mode_note = "_(Screen lock suppressed for simulation testing; session continues)_" if is_simulate else "_(Chronos automated defense engaged; screen session locked)_"

        subject = f"🚨 Chronos-Auth: {'LOCK SIMULATED' if is_simulate else 'LOCKED'} on {hostname}"
        telegram_msg = (
            f"🚨 *CRITICAL SECURITY ALERT*\n"
            f"{lock_headline}\n"
            f"🖥️ *Workstation:* `{hostname}`\n"
            f"⏰ *Time:* `{time.strftime('%H:%M:%S')}`\n"
            f"🛑 *Reason:* {reason}\n\n"
            f"*Feature Attribution & Evidence:*\n{bullet_points}\n\n"
            f"{mode_note}"
        )
        email_body = (
            f"CRITICAL SECURITY ALERT: {'LOCK SIMULATED' if is_simulate else 'WORKSTATION LOCKED'}\n"
            f"======================================================\n\n"
            f"Machine Hostname : {hostname}\n"
            f"Mode             : {lock_mode.upper()}\n"
            f"Triggered At     : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Primary Reason   : {reason}\n\n"
            f"Attribution Evidence:\n{bullet_points}\n\n"
            f"{mode_note}\n"
        )

        lockout_buttons = {
            "inline_keyboard": [
                [
                    {"text": "✅ It's Me (Allow & Continue)", "callback_data": "allow"},
                    {"text": "🔒 Lock Screen Now", "callback_data": "lock"},
                ],
                [
                    {"text": "📸 View Snapshot", "callback_data": "snapshot"}
                ]
            ]
        }

        self._dispatch_async(subject, telegram_msg, email_body, photo_path=snapshot_path, reply_markup=lockout_buttons)

    def notify_walkaway(self) -> None:
        """Dispatches an alert when walk-away proximity lock engages."""
        now = time.time()
        if now - self.last_walkaway_at < self.COOLDOWN_WALKAWAY_SEC:
            return

        self.last_walkaway_at = now
        hostname = socket.gethostname()
        subject = f"📱 Chronos-Auth: Walk-Away Lock Engaged on {hostname}"
        telegram_msg = (
            f"📱 *Walk-Away Lock Engaged*\n"
            f"🖥️ *Workstation:* `{hostname}`\n"
            f"Paired phone signal lost / out of range. Workstation locked automatically."
        )
        email_body = (
            f"Walk-Away Lock Notification\n"
            f"===========================\n\n"
            f"Machine Hostname: {hostname}\n"
            f"Time            : {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"Status          : Paired Bluetooth device signal dropped. Workstation locked.\n"
        )
        self._dispatch_async(subject, telegram_msg, email_body)

    def _dispatch_async(
        self,
        subject: str,
        telegram_msg: str,
        email_body: str,
        photo_path: Optional[Path] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Sends notifications in background thread."""
        def _send():
            self._check_credentials_reload()
            # 1. Telegram
            tg = self.credentials.get("telegram", {})
            if tg.get("enabled", True) and tg.get("token") and tg.get("chat_id"):
                token = tg["token"]
                chat_id = tg["chat_id"]
                if photo_path and photo_path.exists():
                    TelegramClient.send_photo(token, chat_id, photo_path, caption=telegram_msg)
                else:
                    TelegramClient.send_message(token, chat_id, telegram_msg, reply_markup=reply_markup)

            # 2. Email / SMTP
            smtp_cfg = self.credentials.get("smtp", {})
            if smtp_cfg.get("enabled", True) and smtp_cfg.get("host") and smtp_cfg.get("recipient"):
                EmailClient.send_email(smtp_cfg, subject, email_body, attachment_path=photo_path)

            # Cleanup snapshot if temporary
            if photo_path and photo_path.exists():
                try:
                    photo_path.unlink(missing_ok=True)
                except OSError:
                    pass

        threading.Thread(target=_send, daemon=True).start()

    # =========================================================================
    # TELEGRAM BOT REMOTE COMMAND LISTENER (/lock, /status, /snooze, /unlock)
    # =========================================================================
    def _command_poller_loop(self) -> None:
        """Background loop polling Telegram bot updates for authorized remote commands and button callbacks."""
        while self._running:
            try:
                self._check_credentials_reload()
                tg = self.credentials.get("telegram", {})
                token = tg.get("token", "").strip()
                configured_chat_id = str(tg.get("chat_id", "")).strip()

                if not token or not configured_chat_id or not tg.get("enabled", True):
                    time.sleep(3.0)
                    continue

                ok, updates = TelegramClient.get_updates(token, offset=self._last_update_offset, timeout=3)
                if not ok or not updates:
                    time.sleep(1.5)
                    continue

                for update in updates:
                    update_id = update.get("update_id", 0)
                    if update_id >= self._last_update_offset:
                        self._last_update_offset = update_id + 1

                    # 1. Handle interactive inline button clicks (callback queries)
                    cb = update.get("callback_query")
                    if cb:
                        cb_id = str(cb.get("id", ""))
                        sender_chat = str(cb.get("from", {}).get("id", "")).strip()
                        cb_data = str(cb.get("data", "")).strip()
                        if sender_chat == configured_chat_id:
                            hostname = socket.gethostname()
                            if cb_data in ("allow", "unlock"):
                                from chronos_auth.runtime_config import RESET_TRIGGER_PATH, LEGACY_RESET_TRIGGER_PATH
                                for trig in (RESET_TRIGGER_PATH, LEGACY_RESET_TRIGGER_PATH):
                                    try:
                                        trig.touch()
                                    except OSError:
                                        pass
                                self.policy_store.enable_snooze(30)
                                TelegramClient.answer_callback_query(token, cb_id, text="Permission granted! Continuing with full trust.")
                                TelegramClient.send_message(
                                    token, configured_chat_id,
                                    f"✅ *Permission Granted!*\n`{hostname}` is authorized for the next 30 minutes. "
                                    f"You can continue typing uninterrupted even with a lower score."
                                )
                            elif cb_data == "lock":
                                ok, reason = lock_workstation()
                                TelegramClient.answer_callback_query(token, cb_id, text="Workstation locked.")
                                TelegramClient.send_message(
                                    token, configured_chat_id,
                                    f"🔒 *Workstation Locked!*\n`{hostname}` screen session has been secured."
                                )
                            elif cb_data.startswith("snooze"):
                                mins = 15
                                if "_" in cb_data:
                                    try:
                                        mins = int(cb_data.split("_")[1])
                                    except ValueError:
                                        mins = 15
                                self.policy_store.enable_snooze(mins)
                                TelegramClient.answer_callback_query(token, cb_id, text=f"Protection snoozed for {mins}m.")
                                TelegramClient.send_message(
                                    token, configured_chat_id,
                                    f"⏸️ *Protection Snoozed*\nAutomated lockouts are paused for *{mins} minutes* ('Lend PC' mode active)."
                                )
                            elif cb_data == "snapshot":
                                TelegramClient.answer_callback_query(token, cb_id, text="Capturing snapshot...")
                                snap, reason = capture_webcam_snapshot()
                                if snap and snap.exists():
                                    TelegramClient.send_photo(
                                        token, configured_chat_id, snap,
                                        caption=f"📸 Snapshot from `{hostname}` at {time.strftime('%H:%M:%S')}"
                                    )
                                    try:
                                        snap.unlink(missing_ok=True)
                                    except OSError:
                                        pass
                                else:
                                    TelegramClient.send_message(token, configured_chat_id, f"⚠️ Snapshot unavailable: {reason}")
                        else:
                            TelegramClient.answer_callback_query(token, cb_id, text="Access Denied.")
                        continue

                    # 2. Handle standard text messages
                    msg = update.get("message") or update.get("channel_post")
                    if not msg:
                        continue

                    sender_chat = str(msg.get("chat", {}).get("id", "")).strip()
                    text = str(msg.get("text", "")).strip()
                    if not text:
                        continue

                    # Security Verification: strictly check authorized chat ID
                    if sender_chat != configured_chat_id:
                        TelegramClient.send_message(
                            token, sender_chat,
                            f"⛔ *Access Denied*\nYour chat ID (`{sender_chat}`) is not authorized to control Chronos-Auth."
                        )
                        continue

                    self._handle_telegram_command(token, configured_chat_id, text)

            except Exception:
                time.sleep(3.0)

    def _handle_telegram_command(self, token: str, chat_id: str, text: str) -> None:
        """Executes authorized commands sent to Telegram bot."""
        parts = text.split()
        cmd = parts[0].lower().split("@")[0]  # Strip bot handle if present (e.g. /lock@MyBot)

        if cmd in ("/lock", "lock"):
            # Execute Workstation Lockout immediately!
            ok, reason = lock_workstation()
            hostname = socket.gethostname()
            if ok:
                reply = f"🔒 *Workstation Locked!*\n`{hostname}` screen session has been successfully locked remotely."
            else:
                reply = f"⚠️ *Lock Command Issued*\nResult: {reason}"
            TelegramClient.send_message(token, chat_id, reply)

        elif cmd in ("/yes", "yes", "y", "/allow", "allow", "/ok", "ok", "/continue", "continue", "/unlock", "unlock", "/trust", "trust", "/confirm", "confirm"):
            from chronos_auth.runtime_config import RESET_TRIGGER_PATH, LEGACY_RESET_TRIGGER_PATH
            for trig in (RESET_TRIGGER_PATH, LEGACY_RESET_TRIGGER_PATH):
                try:
                    trig.touch()
                except OSError:
                    pass
            self.policy_store.enable_snooze(30)
            reply = (
                f"✅ *Permission Granted!*\n"
                f"Workstation `{socket.gethostname()}` is authorized for the next 30 minutes. "
                f"Session will continue uninterrupted even with a lower score.\n\n"
                f"_(Send `/resume` at any time to re-enable strict lockout checks)_"
            )
            TelegramClient.send_message(token, chat_id, reply)

        elif cmd in ("/status", "status"):
            # Fetch live JSON state
            state_p = self.live_state_path if self.live_state_path.exists() else LEGACY_LIVE_STATE_PATH
            st = read_json(state_p)
            trust = st.get("trust_pct", "—")
            instant = st.get("instant_score_pct", "—")
            action = st.get("action", "Idle / Unknown")
            ctx = st.get("context", "General")
            snoozed = st.get("snoozed", False)
            status_txt = st.get("status_text", action)
            hostname = socket.gethostname()

            reply = (
                f"🛡️ *Chronos-Auth System Status*\n"
                f"🖥️ *Machine:* `{hostname}`\n"
                f"📈 *Cumulative Trust:* `{trust}%`\n"
                f"⚡ *Instant Score:* `{instant}%`\n"
                f"🎯 *Decision:* `{action}`\n"
                f"📂 *Context:* `{ctx}`\n"
                f"⏸️ *Protection State:* `{'Snoozed (' + status_txt + ')' if snoozed else 'Active Monitoring'}`\n"
                f"⏰ *Last Evidence:* `{time.strftime('%H:%M:%S', time.localtime(st.get('timestamp', time.time())))}`"
            )
            TelegramClient.send_message(token, chat_id, reply)

        elif cmd in ("/snooze", "snooze"):
            minutes = 30
            if len(parts) > 1:
                try:
                    minutes = int(parts[1])
                except ValueError:
                    minutes = 30
            self.policy_store.enable_snooze(minutes)
            reply = f"⏸️ *Protection Snoozed*\nAutomated lockouts are paused for *{minutes} minutes* ('Lend PC' mode active)."
            TelegramClient.send_message(token, chat_id, reply)

        elif cmd in ("/resume", "resume", "/resumesnooze"):
            self.policy_store.clear_snooze()
            reply = "▶️ *Protection Resumed*\nContinuous biometric monitoring is now fully active."
            TelegramClient.send_message(token, chat_id, reply)

        elif cmd in ("/snapshot", "snapshot", "/photo", "photo"):
            # Capture snapshot from local camera
            snap, reason = capture_webcam_snapshot()
            if snap and snap.exists():
                TelegramClient.send_photo(
                    token, chat_id, snap,
                    caption=f"📸 Snapshot from `{socket.gethostname()}` at {time.strftime('%H:%M:%S')}"
                )
                try:
                    snap.unlink(missing_ok=True)
                except OSError:
                    pass
            else:
                TelegramClient.send_message(token, chat_id, f"⚠️ Snapshot unavailable: {reason}")

        elif cmd in ("/help", "help", "/start", "start"):
            reply = (
                f"🛡️ *Chronos-Auth Remote Security Bot*\n\n"
                f"*Available Commands:*\n"
                f"• `/unlock` — Confirm identity and reset trust score to 100%\n"
                f"• `/lock` — Instantly lock your workstation screen remotely\n"
                f"• `/status` — View real-time trust score, instant confidence & context\n"
                f"• `/snooze <min>` — Pause automated locks (e.g. `/snooze 30`)\n"
                f"• `/resume` — Immediately resume full protection\n"
                f"• `/snapshot` — Capture and view an instant webcam snapshot\n"
                f"• `/help` — Show this guide\n"
            )
            TelegramClient.send_message(token, chat_id, reply)
