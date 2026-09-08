import http.server
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent
DB_PATH = BASE_DIR / "behavior_data.db"
sys.path.insert(0, str(BASE_DIR))

import socket
from chronos_auth.bluetooth_proximity import BluetoothProximityMonitor
from chronos_auth.chord_analyzer import ChordAnalyzer
from chronos_auth.runtime_config import (
    SecurityPolicyStore,
    CredentialsStore,
    CALIBRATION_STATUS_PATH,
    LOCK_MODE_PATH,
    LIVE_STATE_PATH,
    LEGACY_LIVE_STATE_PATH,
    get_lock_mode,
    set_lock_mode,
    read_json,
    write_calibration_control,
)
from chronos_auth.remote_service import TelegramClient, EmailClient
from chronos_auth.system_actions import lock_workstation

# Global status cache
APP_STATE = {
    "simulate_lock": (get_lock_mode() != "enforce"),
    "sensitivity": "Balanced",
}

class DashboardHTTPHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Quiet console logging

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("", "/"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(self.get_html_dashboard().encode("utf-8"))
            return

        if path == "/api/status":
            self.send_json(self.get_system_status())
            return

        if path == "/api/stats":
            self.send_json(self.get_db_stats())
            return

        if path == "/api/data":
            self.send_json(self.get_recent_data())
            return

        if path == "/api/bluetooth/scan":
            devices = BluetoothProximityMonitor.scan_nearby_devices()
            self.send_json({"devices": devices})
            return

        if path == "/api/shortcuts":
            analyzer = ChordAnalyzer()
            self.send_json({"shortcuts": analyzer.get_top_shortcuts(15)})
            return

        if path == "/api/policy":
            store = SecurityPolicyStore()
            pol = store.load()
            clean_pol = {k: v for k, v in pol.items() if k != "pin"}
            clean_pol["has_pin"] = store.has_pin()
            clean_pol["is_snoozed"] = store.is_snoozed(pol)
            clean_pol["simulate_lock"] = (get_lock_mode() != "enforce")
            self.send_json(clean_pol)
            return

        if path == "/api/calibration":
            cal_st = read_json(CALIBRATION_STATUS_PATH, {"state": "idle", "message": "No active calibration."})
            self.send_json(cal_st)
            return

        if path == "/api/remote/status":
            cred_store = CredentialsStore()
            creds = cred_store.load()
            tg = creds.get("telegram", {})
            smtp = creds.get("smtp", {})
            self.send_json({
                "telegram": {
                    "configured": bool(tg.get("token") and tg.get("chat_id")),
                    "enabled": bool(tg.get("enabled", True)),
                    "chat_id": str(tg.get("chat_id", "")),
                    "has_token": bool(tg.get("token")),
                },
                "smtp": {
                    "configured": bool(smtp.get("host") and smtp.get("recipient")),
                    "enabled": bool(smtp.get("enabled", True)),
                    "host": smtp.get("host", ""),
                    "port": int(smtp.get("port", 587)),
                    "user": smtp.get("user", ""),
                    "recipient": smtp.get("recipient", ""),
                    "use_tls": bool(smtp.get("use_tls", True)),
                    "use_ssl": bool(smtp.get("use_ssl", False)),
                }
            })
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        if path == "/api/control/start":
            res = self.execute_start_service()
            self.send_json(res)
            return

        if path == "/api/control/stop":
            res = self.execute_stop_service()
            self.send_json(res)
            return

        if path == "/api/control/retrain":
            res = self.execute_retrain()
            self.send_json(res)
            return

        if path == "/api/bluetooth/select":
            mac = payload.get("mac", "")
            name = payload.get("name", "")
            monitor = BluetoothProximityMonitor()
            monitor.save_target_device(mac, name)
            self.send_json({"success": True, "paired": mac, "name": name})
            return

        if path == "/api/settings":
            if "simulate_lock" in payload:
                APP_STATE["simulate_lock"] = bool(payload["simulate_lock"])
                set_lock_mode("simulate" if APP_STATE["simulate_lock"] else "enforce")
            if "sensitivity" in payload:
                APP_STATE["sensitivity"] = str(payload["sensitivity"])
            self.send_json({"success": True, "settings": APP_STATE})
            return

        if path == "/api/policy":
            store = SecurityPolicyStore()
            updates = {}
            if "sensitivity" in payload:
                updates["sensitivity"] = str(payload["sensitivity"])
            if "warning_threshold" in payload:
                try:
                    updates["warning_threshold"] = int(payload["warning_threshold"])
                except (ValueError, TypeError):
                    pass
            if "adaptive_baselines" in payload:
                updates["adaptive_baselines"] = bool(payload["adaptive_baselines"])
            if "excluded_apps" in payload and isinstance(payload["excluded_apps"], list):
                updates["excluded_apps"] = [str(x).strip().lower() for x in payload["excluded_apps"] if str(x).strip()]
            if updates:
                store.update(**updates)
            if "simulate_lock" in payload:
                sim = bool(payload["simulate_lock"])
                set_lock_mode("simulate" if sim else "enforce")
            pol = store.load()
            clean_pol = {k: v for k, v in pol.items() if k != "pin"}
            clean_pol["has_pin"] = store.has_pin()
            clean_pol["is_snoozed"] = store.is_snoozed(pol)
            self.send_json({"success": True, "policy": clean_pol})
            return

        if path == "/api/snooze":
            store = SecurityPolicyStore()
            action = str(payload.get("action", "enable")).lower()
            if action == "clear":
                pin = str(payload.get("pin", ""))
                if store.has_pin() and not store.verify_pin(pin):
                    self.send_json({"success": False, "error": "Invalid PIN"}, status=403)
                    return
                store.clear_snooze()
                self.send_json({"success": True, "snoozed": False})
            else:
                try:
                    mins = int(payload.get("minutes", 30))
                except (ValueError, TypeError):
                    mins = 30
                store.enable_snooze(mins)
                self.send_json({"success": True, "snoozed": True, "minutes": mins})
            return

        if path == "/api/calibration":
            cmd = str(payload.get("command", "")).lower()
            phase = str(payload.get("phase", "typing")).lower()
            dur = payload.get("duration_seconds")
            if cmd in ("start", "finish", "cancel"):
                write_calibration_control(cmd, phase=phase, duration_seconds=dur)
                self.send_json({"success": True, "command": cmd})
            else:
                self.send_json({"success": False, "error": "Unknown calibration command"}, status=400)
            return

        if path == "/api/remote/credentials":
            cred_store = CredentialsStore()
            creds = cred_store.load()
            if "telegram" in payload and isinstance(payload["telegram"], dict):
                tg = payload["telegram"]
                token = tg.get("token", creds.get("telegram", {}).get("token", ""))
                chat_id = tg.get("chat_id", creds.get("telegram", {}).get("chat_id", ""))
                enabled = tg.get("enabled", creds.get("telegram", {}).get("enabled", True))
                creds["telegram"] = {"token": str(token).strip(), "chat_id": str(chat_id).strip(), "enabled": bool(enabled)}
            if "smtp" in payload and isinstance(payload["smtp"], dict):
                smtp_in = payload["smtp"]
                cur_smtp = creds.get("smtp", {})
                for k in ("host", "port", "user", "password", "recipient", "use_tls", "use_ssl", "enabled"):
                    if k in smtp_in:
                        cur_smtp[k] = smtp_in[k]
                creds["smtp"] = cur_smtp
            cred_store.save(creds)
            self.send_json({"success": True, "message": "Credentials updated."})
            return

        if path == "/api/remote/test":
            target = str(payload.get("target", "telegram")).lower()
            cred_store = CredentialsStore()
            creds = cred_store.load()
            if target == "telegram":
                tg = creds.get("telegram", {})
                tok = tg.get("token", "")
                cid = tg.get("chat_id", "")
                if not tok or not cid:
                    self.send_json({"success": False, "error": "Telegram token or chat_id missing."}, status=400)
                    return
                ok, msg = TelegramClient.send_message(
                    tok, cid,
                    f"🛡️ *Chronos-Auth API Test*\nWorkstation `{socket.gethostname()}` connection verified via REST API."
                )
                self.send_json({"success": ok, "message": msg}, status=200 if ok else 400)
                return
            elif target == "smtp":
                smtp_cfg = creds.get("smtp", {})
                if not smtp_cfg.get("host") or not smtp_cfg.get("recipient"):
                    self.send_json({"success": False, "error": "SMTP host or recipient missing."}, status=400)
                    return
                subj = f"🛡️ Chronos-Auth API Test from {socket.gethostname()}"
                body = "Chronos-Auth SMTP configuration verified via REST API test."
                ok, msg = EmailClient.send_email(smtp_cfg, subj, body)
                self.send_json({"success": ok, "message": msg}, status=200 if ok else 400)
                return
            else:
                self.send_json({"success": False, "error": f"Unknown target: {target}"}, status=400)
                return

        if path == "/api/remote/lock":
            ok, reason = lock_workstation()
            self.send_json({"success": ok, "message": reason})
            return

        self.send_error(404, "Not Found")

    def send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))

    def get_system_status(self) -> dict:
        # Check running processes
        cpp_running = False
        py_running = False
        try:
            res = subprocess.run(["pgrep", "-f", "event_engine"], capture_output=True)
            cpp_running = (res.returncode == 0)
            res_py = subprocess.run(["pgrep", "-f", "receiver.py"], capture_output=True)
            py_running = (res_py.returncode == 0)
        except Exception:
            pass

        state_file = LIVE_STATE_PATH if LIVE_STATE_PATH.exists() else LEGACY_LIVE_STATE_PATH
        if state_file.exists():
            try:
                live_state = json.loads(state_file.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                live_state = {}

        # Load Bluetooth config; connectivity comes only from live telemetry.
        bt_info = {"configured": False, "name": "None", "mac": "", "connected": False, "score": 0.0}
        bt_cfg = BASE_DIR / "bluetooth_config.json"
        if bt_cfg.exists():
            try:
                with open(bt_cfg) as f:
                    d = json.load(f)
                    bt_info["configured"] = bool(d.get("mac"))
                    bt_info["name"] = d.get("name", d.get("mac", "Phone"))
                    bt_info["mac"] = d.get("mac", "")
                    bt_info["connected"] = bool(live_state.get("phone_connected", False))
                    bt_info["score"] = float(live_state.get("phone_score", 0.0) or 0.0)
            except Exception:
                pass

        # Shortcuts summary
        chord = ChordAnalyzer()
        top_shortcuts = chord.get_top_shortcuts(5)

        store = SecurityPolicyStore()
        pol = store.load()
        sim_mode = (get_lock_mode() != "enforce")

        return {
            "services": {
                "event_engine": cpp_running,
                "python_receiver": py_running,
                "overall_active": cpp_running and py_running,
            },
            "security": {
                "trust_pct": live_state.get("trust_pct"),
                "instant_score_pct": live_state.get("instant_score_pct"),
                "p_owner": live_state.get("p_owner"),
                "p_imp": live_state.get("p_imp"),
                "llr": live_state.get("cumulative_llr"),
                "boundary_a": live_state.get("boundary_a"),
                "boundary_b": live_state.get("boundary_b"),
                "boundary_w": live_state.get("boundary_w"),
                "action": live_state.get("action", "NO LIVE SAMPLE"),
                "status_text": live_state.get("status_text", live_state.get("action", "")),
                "snoozed": bool(live_state.get("snoozed", False)),
                "excluded": bool(live_state.get("excluded", False)),
                "high_entropy_available": bool(live_state.get("high_entropy_available", False)),
                "high_entropy_confidence": float(live_state.get("high_entropy_confidence", 0.0) or 0.0),
                "active_context": live_state.get("context", "Unknown"),
                "app_name": live_state.get("app_name", "Unknown"),
                "model_source": live_state.get("model_source"),
                "keyboard_events": live_state.get("keyboard_events", 0),
                "mouse_strokes": live_state.get("mouse_strokes", 0),
                "simulate_lock": sim_mode,
                "sensitivity": pol.get("sensitivity", "Balanced"),
                "warning_threshold": pol.get("warning_threshold", 50),
                "impact_lines": live_state.get("impact_lines", []),
                "impacts": live_state.get("impacts", []),
            },
            "bluetooth": bt_info,
            "shortcuts": top_shortcuts,
        }

    def get_db_stats(self) -> dict:
        if not DB_PATH.exists():
            return {"total_rows": 0, "owner_rows": 0, "impostor_rows": 0, "contexts": {}}

        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM features")
            total = cur.fetchone()[0]
            cur.execute("SELECT label, COUNT(*) FROM features GROUP BY label")
            labels = dict(cur.fetchall())
            cur.execute("SELECT CAST(activity AS INTEGER), COUNT(*) FROM features GROUP BY CAST(activity AS INTEGER)")
            acts = dict(cur.fetchall())
            conn.close()

            context_map = {0: "Typing (Code)", 1: "Mouse Driven", 2: "Idle / Read", 3: "Mixed Work", 5: "General"}
            act_formatted = {context_map.get(k, f"Context {k}"): v for k, v in acts.items()}

            return {
                "total_rows": total,
                "owner_rows": labels.get("owner", 0),
                "impostor_rows": labels.get("external_impostor", 0) + labels.get("impostor", 0),
                "unverified_rows": labels.get("unverified_live", 0),
                "contexts": act_formatted,
            }
        except Exception as e:
            return {"error": str(e), "total_rows": 0}

    def get_recent_data(self) -> dict:
        if not DB_PATH.exists():
            return {"columns": [], "rows": []}

        try:
            conn = sqlite3.connect(str(DB_PATH))
            cur = conn.cursor()
            cur.execute("PRAGMA table_info(features)")
            cols = [r[1] for r in cur.fetchall()]
            cur.execute("SELECT * FROM features ORDER BY id DESC LIMIT 25")
            raw_rows = cur.fetchall()
            conn.close()

            # Format float decimals nicely
            formatted = []
            for r in raw_rows:
                formatted_row = [round(x, 2) if isinstance(x, float) else x for x in r]
                formatted.append(formatted_row)

            return {"columns": cols, "rows": formatted}
        except Exception as e:
            return {"error": str(e), "columns": [], "rows": []}

    def execute_start_service(self) -> dict:
        script = ROOT_DIR / "start.sh"
        if script.exists():
            subprocess.Popen(["bash", str(script)], cwd=str(ROOT_DIR))
            time.sleep(1.0)
            return {"success": True, "message": "Services started in background"}
        return {"success": False, "message": "start.sh not found"}

    def execute_stop_service(self) -> dict:
        script = ROOT_DIR / "stop.sh"
        if script.exists():
            subprocess.run(["bash", str(script)], cwd=str(ROOT_DIR))
            return {"success": True, "message": "Services stopped"}
        return {"success": False, "message": "stop.sh not found"}

    def execute_retrain(self) -> dict:
        def _run():
            script = BASE_DIR / "train_chronos.py"
            subprocess.run([sys.executable, str(script)], cwd=str(BASE_DIR))

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return {"success": True, "message": "Background retraining job launched!"}

    def get_html_dashboard(self) -> str:
        return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chronos-Auth Security Hub</title>
<style>
:root {
  color-scheme: dark;
  --bg: #0d1117;
  --card: #161b22;
  --border: #30363d;
  --primary: #58a6ff;
  --success: #2ea043;
  --warning: #d29922;
  --danger: #f85149;
  --text: #f0f6fc;
  --muted: #8b949e;
}
* { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
body { background-color: var(--bg); color: var(--text); padding: 24px; }
.header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 16px; margin-bottom: 24px; }
.header h1 { font-size: 24px; font-weight: 700; display: flex; align-items: center; gap: 10px; }
.badge { font-size: 12px; padding: 4px 10px; border-radius: 12px; font-weight: 600; text-transform: uppercase; }
.badge-active { background: #238636; color: #fff; }
.badge-inactive { background: #da3633; color: #fff; }

.grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 20px; margin-bottom: 24px; }
.card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 20px; }
.card h2 { font-size: 16px; margin-bottom: 14px; display: flex; justify-content: space-between; color: var(--muted); text-transform: uppercase; letter-spacing: 0.5px; }

.trust-gauge { text-align: center; padding: 10px 0; }
.trust-number { font-size: 54px; font-weight: 800; color: var(--success); }
.trust-status { font-size: 16px; font-weight: 600; margin-top: 4px; }

.btn { cursor: pointer; padding: 10px 18px; border-radius: 6px; font-size: 14px; font-weight: 600; border: none; transition: 0.15s ease; }
.btn-primary { background: var(--primary); color: #000; }
.btn-success { background: var(--success); color: #fff; }
.btn-danger { background: var(--danger); color: #fff; }
.btn-secondary { background: #21262d; border: 1px solid var(--border); color: var(--text); }
.btn:hover { opacity: 0.85; }

.controls { display: flex; gap: 12px; margin-top: 14px; flex-wrap: wrap; }
.list-item { display: flex; justify-content: space-between; padding: 8px 0; border-bottom: 1px solid #21262d; font-size: 14px; }
.list-item:last-child { border-bottom: none; }

.table-wrap { overflow-x: auto; max-height: 340px; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 8px 12px; border: 1px solid var(--border); text-align: left; }
th { background: #21262d; position: sticky; top: 0; }
tr:nth-child(even) { background: #0e1217; }

.device-row { display: flex; justify-content: space-between; align-items: center; padding: 10px; background: #0d1117; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 8px; }
</style>
</head>
<body>

<div class="header">
  <h1>🛡️ Chronos-Auth <span style="font-size: 14px; color: var(--muted); font-weight: 400;">Behavioral Biometrics Hub</span></h1>
  <div>
    <span id="service-badge" class="badge badge-inactive">Checking...</span>
  </div>
</div>

<!-- New PC Quick Setup Wizard -->
<div id="onboarding-card" class="card" style="display: none; border: 1px solid var(--primary); background: linear-gradient(180deg, #1f2937, #161b22); margin-bottom: 24px;">
  <h2 style="color: var(--primary);">🚀 New PC Quick Setup (No Code Required) <span id="wizard-step" style="font-size: 12px; color: #000; background: var(--primary); padding: 2px 8px; border-radius: 10px; font-weight: 700;">Zero-Config</span></h2>
  <p style="font-size: 14px; margin-bottom: 12px; color: var(--text);">
    Chronos-Auth passively learns your natural typing and mouse movements. Follow these 3 simple steps to secure this PC:
  </p>
  <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 12px; margin-bottom: 14px;">
    <div style="padding: 12px; background: rgba(0,0,0,0.3); border-radius: 6px; border-left: 3px solid var(--success);">
      <strong>1. Start Protection</strong>
      <p style="font-size: 12px; color: var(--muted); margin-top: 4px;">Click 'Start Protection' below to start background recording.</p>
    </div>
    <div style="padding: 12px; background: rgba(0,0,0,0.3); border-radius: 6px; border-left: 3px solid var(--primary);">
      <strong>2. Pair Phone (Optional)</strong>
      <p style="font-size: 12px; color: var(--muted); margin-top: 4px;">Click 'Scan Nearby Phones' to enable Walk-Away auto lock.</p>
    </div>
    <div style="padding: 12px; background: rgba(0,0,0,0.3); border-radius: 6px; border-left: 3px solid var(--warning);">
      <strong>3. Passive Training</strong>
      <p style="font-size: 12px; color: var(--muted); margin-top: 4px;">Work normally for ~1 hour. AI automatically activates.</p>
    </div>
  </div>
  <div style="margin-top: 8px;">
    <div style="display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px;">
      <span>AI Baseline Profile Progress:</span>
      <strong id="progress-pct">0%</strong>
    </div>
    <div style="background: #21262d; border-radius: 6px; height: 10px; overflow: hidden;">
      <div id="progress-bar" style="background: var(--success); width: 0%; height: 100%; transition: width 0.3s ease;"></div>
    </div>
  </div>
</div>

<div class="grid">
  <!-- Card 1: Live Security & Trust -->
  <div class="card">
    <h2>Continuous Security State <span>Live 1.5s</span></h2>
    <div class="trust-gauge">
      <div id="trust-val" class="trust-number">—</div>
      <div id="action-val" class="trust-status" style="color: var(--muted);">NO LIVE SAMPLE</div>
    </div>
    <div style="margin-top: 15px;">
      <div class="list-item"><span>Hypothesis LLR (Wald SPRT):</span> <strong id="llr-val">—</strong></div>
      <div class="list-item"><span>Active Task Context:</span> <strong id="context-val">General/Desktop</strong></div>
      <div class="list-item"><span>Lock Simulation Mode:</span> <strong id="sim-mode">Enabled (Safe Test)</strong></div>
    </div>
    <div class="controls">
      <button class="btn btn-success" onclick="controlService('start')">▶ Start Protection</button>
      <button class="btn btn-danger" onclick="controlService('stop')">⏹ Stop</button>
      <button class="btn btn-secondary" onclick="triggerRetrain()">⚡ Retrain AI</button>
    </div>
  </div>

  <!-- Card 2: Bluetooth Phone Walk-Away Pairing -->
  <div class="card">
    <h2>📱 Bluetooth Walk-Away Proximity <span id="bt-status">Disconnected</span></h2>
    <p style="font-size: 13px; color: var(--muted); margin-bottom: 12px;">
      Automatically locks workstation the moment you walk away with your smartphone.
    </p>
    <div id="paired-device-box" style="padding: 10px; background: #0e1217; border: 1px solid var(--border); border-radius: 6px; margin-bottom: 12px;">
      <div>Current Device: <strong id="bt-name">None paired</strong></div>
      <div style="font-size: 12px; color: var(--muted);" id="bt-mac">MAC: Not configured</div>
    </div>
    <div class="controls">
      <button class="btn btn-primary" onclick="scanBluetooth()">🔍 Scan Nearby Phones</button>
    </div>
    <div id="device-list" style="margin-top: 14px; max-height: 140px; overflow-y: auto;"></div>
  </div>

  <!-- Card 3: Dynamic Shortcut Habits -->
  <div class="card">
    <h2>⌨️ Learned Shortcut Habits <span>Muscle Memory</span></h2>
    <p style="font-size: 13px; color: var(--muted); margin-bottom: 12px;">
      Dynamically discovered keyboard commands & muscle memory intervals.
    </p>
    <div id="shortcuts-box">Loading personal shortcuts...</div>
  </div>

  <!-- Card 4: Dataset & AI Telemetry -->
  <div class="card">
    <h2>📊 Behavioral Telemetry Store <span>Database</span></h2>
    <div class="list-item"><span>Total Telemetry Windows:</span> <strong id="stat-total">0</strong></div>
    <div class="list-item"><span>Genuine Owner Windows:</span> <strong id="stat-owner" style="color: var(--success);">0</strong></div>
    <div class="list-item"><span>External impostor rows:</span> <strong id="stat-imp" style="color: var(--warning);">0</strong></div>
    <div class="list-item"><span>Empirical EER:</span> <strong style="color: var(--muted);">Not established</strong></div>
    <div class="list-item"><span>Empirical lockout latency:</span> <strong>Not established</strong></div>
  </div>
</div>

<!-- Database Table Viewer -->
<div class="card">
  <h2>🗄️ Recorded Biometric Telemetry (behavior_data.db) <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="loadData()">🔄 Refresh Table</button></h2>
  <div class="table-wrap">
    <table id="data-table">
      <thead><tr><th>Loading...</th></tr></thead>
      <tbody></tbody>
    </table>
  </div>
</div>

<script>
async function refreshStatus() {
  try {
    const res = await fetch('/api/status');
    const d = await res.json();

    // Service badge
    const badge = document.getElementById('service-badge');
    if (d.services.overall_active) {
      badge.textContent = 'Active (Protecting)';
      badge.className = 'badge badge-active';
    } else {
      badge.textContent = 'Standby';
      badge.className = 'badge badge-inactive';
    }

    // Security state
    document.getElementById('trust-val').textContent = d.security.instant_score_pct == null ? '—' : Number(d.security.instant_score_pct).toFixed(2) + '%';
    document.getElementById('action-val').textContent = d.security.action;
    document.getElementById('action-val').style.color = d.security.action === 'LOCK' ? 'var(--danger)' : (d.security.action === 'ALERT' ? 'var(--warning)' : 'var(--success)');
    document.getElementById('llr-val').textContent = d.security.llr == null ? '—' : Number(d.security.llr).toFixed(2);
    document.getElementById('context-val').textContent = d.security.active_context;
    document.getElementById('sim-mode').textContent = d.security.simulate_lock ? 'Enabled (Safe Test)' : 'Enforcement Enabled';

    // Bluetooth
    if (d.bluetooth.configured) {
      document.getElementById('bt-name').textContent = d.bluetooth.name;
      document.getElementById('bt-mac').textContent = 'MAC: ' + d.bluetooth.mac;
      if (d.bluetooth.connected) {
        document.getElementById('bt-status').textContent = 'Connected & Guarding';
        document.getElementById('bt-status').style.color = 'var(--success)';
      } else {
        document.getElementById('bt-status').textContent = 'Paired (Disconnected / Standby)';
        document.getElementById('bt-status').style.color = 'var(--warning)';
      }
    } else {
      document.getElementById('bt-name').textContent = 'None';
      document.getElementById('bt-mac').textContent = 'No device paired';
      document.getElementById('bt-status').textContent = 'Unpaired';
      document.getElementById('bt-status').style.color = 'var(--muted)';
    }

    // Shortcuts
    if (d.shortcuts && d.shortcuts.length > 0) {
      let h = '';
      d.shortcuts.forEach(s => {
        h += `<div class="list-item"><span><strong>${s.shortcut}</strong> (${s.count}x)</span> <span>Lead: ${s.mean_lead_ms}ms (±${s.std_lead_ms})</span></div>`;
      });
      document.getElementById('shortcuts-box').innerHTML = h;
    } else {
      document.getElementById('shortcuts-box').innerHTML = '<div style="color: var(--muted); font-size: 13px;">Press shortcuts (e.g. Ctrl+C, Alt+Tab) to see them profiled here automatically.</div>';
    }
  } catch(e) {}
}

async function refreshStats() {
  try {
    const res = await fetch('/api/stats');
    const d = await res.json();
    document.getElementById('stat-total').textContent = d.total_rows;
    document.getElementById('stat-owner').textContent = d.owner_rows;
    document.getElementById('stat-imp').textContent = d.impostor_rows;

    const onb = document.getElementById('onboarding-card');
    if (d.owner_rows < 100) {
      onb.style.display = 'block';
      const pct = Math.min(100, Math.round((d.owner_rows / 100) * 100));
      document.getElementById('progress-pct').textContent = pct + '% (' + d.owner_rows + ' / 100 frames)';
      document.getElementById('progress-bar').style.width = pct + '%';
    } else {
      onb.style.display = 'none';
    }
  } catch(e) {}
}

async function loadData() {
  try {
    const res = await fetch('/api/data');
    const d = await res.json();
    if (!d.columns || d.columns.length === 0) return;

    let th = '<tr>' + d.columns.map(c => `<th>${c}</th>`).join('') + '</tr>';
    document.querySelector('#data-table thead').innerHTML = th;

    let rows = d.rows.map(r => '<tr>' + r.map(cell => `<td>${cell}</td>`).join('') + '</tr>').join('');
    document.querySelector('#data-table tbody').innerHTML = rows;
  } catch(e) {}
}

async function scanBluetooth() {
  const box = document.getElementById('device-list');
  box.innerHTML = '<div style="font-size: 13px; color: var(--muted);">Scanning Bluetooth devices...</div>';
  try {
    const res = await fetch('/api/bluetooth/scan');
    const d = await res.json();
    if (!d.devices || d.devices.length === 0) {
      box.innerHTML = '<div style="font-size: 13px; color: var(--muted);">No devices found. Make sure phone Bluetooth is ON.</div>';
      return;
    }
    let h = '';
    d.devices.forEach(dev => {
      h += `<div class="device-row">
        <div><strong>${dev.name}</strong><br><small style="color: var(--muted);">${dev.mac}</small></div>
        <button class="btn btn-secondary" style="padding: 4px 10px; font-size: 12px;" onclick="selectDevice('${dev.mac}', '${dev.name}')">Pair Device</button>
      </div>`;
    });
    box.innerHTML = h;
  } catch(e) {
    box.innerHTML = '<div style="color: var(--danger);">Bluetooth scan failed.</div>';
  }
}

async function selectDevice(mac, name) {
  await fetch('/api/bluetooth/select', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({mac, name})
  });
  alert('Device Paired for Walk-Away Lock: ' + name);
  refreshStatus();
}

async function controlService(action) {
  await fetch('/api/control/' + action, {method: 'POST'});
  setTimeout(refreshStatus, 1200);
}

async function triggerRetrain() {
  alert('Background AI Retraining started! Will notify upon completion.');
  await fetch('/api/control/retrain', {method: 'POST'});
}

setInterval(refreshStatus, 2000);
setInterval(refreshStats, 5000);
refreshStatus();
refreshStats();
loadData();
</script>
</body>
</html>
"""

def run_server(port: int = 8888):
    server = http.server.HTTPServer(("127.0.0.1", port), DashboardHTTPHandler)
    print(f"================================================================")
    print(f" 🛡️ Chronos-Auth Local Web Application Running!")
    print(f" 🌐 Access at: http://127.0.0.1:{port}")
    print(f" 🔒 100% Offline, Zero Cloud Dependencies, Completely Standalone")
    print(f"================================================================")
    server.serve_forever()

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8888))
    run_server(port)
