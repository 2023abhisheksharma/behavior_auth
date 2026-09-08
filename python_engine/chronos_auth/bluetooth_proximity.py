import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, Tuple

class BluetoothProximityMonitor:
    """
    Passively monitors Bluetooth RSSI (signal strength) of paired smartphone or smartwatch.
    Provides Walk-Away detection: if the user walks away with their phone, trust drops
    or triggers workstation lock immediately.
    """

    def __init__(self, target_mac: Optional[str] = None, poll_interval: float = 2.5):
        self.target_mac = target_mac or os.getenv("BEHAVIOR_BLUETOOTH_MAC", "")
        self.poll_interval = poll_interval

        self.last_rssi: Optional[int] = None
        self.is_connected: bool = False
        self.proximity_score: float = 0.0  # 1.0 = present, 0.0 = unavailable/not present
        self.walk_away_triggered: bool = False

        self._running = False
        self._thread: Optional[threading.Thread] = None

        self.has_bluetoothctl = shutil.which("bluetoothctl") is not None
        self.config_path = Path(__file__).parent.parent / "bluetooth_config.json"
        self.last_reconnect_attempt = 0.0
        self._load_config()
        self._auto_discover_device()

        # Immediate initial check
        try:
            score, connected, rssi = self._check_proximity()
            self.proximity_score = score
            self.is_connected = connected
            self.last_rssi = rssi
        except Exception:
            pass

        self.was_connected = False
        self.disconnected_since = 0.0
        self.start()

    def _load_config(self):
        """Loads saved target device from bluetooth_config.json."""
        if self.config_path.exists():
            try:
                import json
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                    if data.get("mac"):
                        self.target_mac = data["mac"]
            except Exception:
                pass

    def save_target_device(self, mac: str, name: str = ""):
        """Saves selected phone/device so it stays connected across app launches."""
        self.target_mac = mac
        try:
            import json
            with open(self.config_path, "w") as f:
                json.dump({"mac": mac, "name": name, "updated_at": time.time()}, f, indent=2)
            print(f"[Bluetooth] Target device saved: {name} ({mac})")
        except Exception as e:
            print(f"[Bluetooth] Failed to save config: {e}")

    @staticmethod
    def scan_nearby_devices() -> list:
        """Scans for paired, connected, and nearby Bluetooth devices with friendly names."""
        devices = []
        seen = set()

        if not shutil.which("bluetoothctl"):
            return []

        for subcmd in ["Connected", "Paired", ""]:
            try:
                cmd = ["bluetoothctl", "devices"]
                if subcmd:
                    cmd.append(subcmd)
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=1.5)
                if res.returncode == 0:
                    for line in res.stdout.strip().splitlines():
                        parts = line.split()
                        if len(parts) >= 2 and parts[0] == "Device":
                            mac = parts[1]
                            if mac not in seen:
                                seen.add(mac)
                                name = " ".join(parts[2:]) if len(parts) > 2 else "Unknown Device"
                                devices.append({"mac": mac, "name": name, "connected": subcmd == "Connected"})
            except Exception:
                pass

        return devices

    def _auto_discover_device(self):
        """Auto-discovers connected or paired phone if MAC not explicitly configured."""
        if self.target_mac or not self.has_bluetoothctl:
            return

        try:
            res = subprocess.run(
                ["bluetoothctl", "devices", "Connected"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                for line in res.stdout.strip().splitlines():
                    parts = line.split()
                    if len(parts) >= 2 and parts[0] == "Device":
                        self.target_mac = parts[1]
                        print(f"[Bluetooth] Auto-paired with connected device: {self.target_mac}")
                        break
        except Exception:
            pass

    def start(self):
        """Starts background RSSI polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _poll_loop(self):
        last_scan_time = 0.0
        while self._running:
            try:
                # Run a quick background passive discovery every 18 seconds to keep BlueZ RSSI cache warm
                now = time.time()
                if self.has_bluetoothctl and (now - last_scan_time > 18.0):
                    last_scan_time = now
                    threading.Thread(target=self._trigger_passive_scan, daemon=True).start()

                score, is_present, rssi = self._check_proximity()
                self.proximity_score = score
                self.is_connected = is_present  # Tells callers phone is present without hijacking audio
                self.last_rssi = rssi

                if is_present:
                    self.was_connected = True
                    self.disconnected_since = 0.0
                    if rssi is not None and rssi < -88:
                        self.walk_away_triggered = True
                    else:
                        self.walk_away_triggered = False
                else:
                    # Phone not seen in this poll
                    if self.was_connected:
                        if self.disconnected_since == 0.0:
                            self.disconnected_since = now
                        if (now - self.disconnected_since) > 25.0:
                            self.walk_away_triggered = True
                    else:
                        self.walk_away_triggered = False

            except Exception:
                self.proximity_score = 0.0
                self.is_connected = False
                self.last_rssi = None
                self.walk_away_triggered = False

            time.sleep(self.poll_interval)

    def _trigger_passive_scan(self):
        """Runs a brief 2-second passive discovery to refresh nearby device beacons without connecting."""
        if not self.has_bluetoothctl:
            return
        try:
            subprocess.run(
                ["bluetoothctl", "--timeout", "2", "scan", "on"],
                capture_output=True,
                text=True,
                timeout=3.0,
            )
        except Exception:
            pass

    def _probe_baseband(self, mac: str, timeout: float = 1.2) -> Tuple[bool, Optional[float]]:
        """
        Probes device presence at the Bluetooth radio baseband layer.
        Does NOT establish A2DP or HFP audio links, leaving phone audio completely unaffected.
        """
        import socket
        t0 = time.time()
        s = None
        try:
            s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
            s.settimeout(timeout)
            # Channel 29: non-audio dummy channel.
            # If phone is in radio range, it will reply to the baseband page with ACK/RST.
            s.connect((mac, 29))
            rtt_ms = (time.time() - t0) * 1000.0
            return True, rtt_ms
        except ConnectionRefusedError:
            # Phone responded over the air immediately (device is physically nearby!)
            rtt_ms = (time.time() - t0) * 1000.0
            return True, rtt_ms
        except (TimeoutError, OSError):
            return False, None
        finally:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass

    def connect_device(self, mac: Optional[str] = None) -> bool:
        """
        Selects device as target for proximity monitoring.
        DOES NOT connect audio profiles so phone audio is never hijacked.
        """
        target = mac or self.target_mac
        if not target:
            return False
        self.target_mac = target
        # Test proximity non-intrusively
        score, present, rssi = self._check_proximity()
        self.proximity_score = score
        self.is_connected = present
        self.last_rssi = rssi
        return present

    def _check_proximity(self) -> Tuple[float, bool, Optional[int]]:
        """
        Passively checks if the target phone is nearby and estimates proximity.
        Never invokes audio sinks or connections that interrupt phone audio/calls.
        """
        if not self.target_mac or not self.has_bluetoothctl:
            return 0.0, False, None

        rssi = None
        is_connected_kernel = False

        try:
            res = subprocess.run(
                ["bluetoothctl", "info", self.target_mac],
                capture_output=True,
                text=True,
                timeout=1.2,
            )
            if res.returncode == 0:
                out = res.stdout
                is_connected_kernel = "Connected: yes" in out
                for line in out.splitlines():
                    if "RSSI:" in line:
                        try:
                            rssi = int(line.split("RSSI:")[1].split()[0])
                        except Exception:
                            pass

        except Exception:
            pass

        # 1. If RSSI is reported by BlueZ (from connected state or passive beacon scan)
        if rssi is not None:
            if rssi >= -65:
                score = 1.0   # Strong proximity (< 1.5m)
            elif rssi >= -75:
                score = 0.85  # Normal proximity (~2m)
            elif rssi >= -85:
                score = 0.50  # Room boundary (~3-4m)
            else:
                score = 0.20  # Far (> 5m)
            return score, True, rssi

        # 2. If connected at kernel level but no RSSI reported
        if is_connected_kernel:
            return 0.80, True, None

        # 3. If unconnected, probe radio baseband without audio profile connection
        responded, rtt_ms = self._probe_baseband(self.target_mac, timeout=1.0)
        if responded and rtt_ms is not None:
            if rtt_ms < 250.0:
                score = 0.85  # Nearby (< 2m)
            elif rtt_ms < 600.0:
                score = 0.65  # Medium distance
            else:
                score = 0.40  # Boundary
            return score, True, None

        # 4. Device did not respond
        return 0.0, False, None

    def get_status(self) -> Tuple[float, bool, bool]:
        """Returns (proximity_score, is_connected, is_walk_away_detected)."""
        return self.proximity_score, self.is_connected, self.walk_away_triggered
