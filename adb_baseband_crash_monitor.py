#!/usr/bin/env python3
"""Standalone ADB monitor for baseband/modem crash signals.

The script follows the same broad idea as 5Ghoul's MonitorADB: run adb logcat,
scan selected log buffers, and emit a crash event when modem-related magic
words are seen. It is intentionally device-agnostic, with presets for OnePlus
and Pixel phones.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable


COMMON_PATTERNS = [
    r"\bModemEvent:\s*modem_failure\b",
    r"\bModemRestartStats\b",
    r"\bmodem(?:[_ -]subsystem)?(?:[_ -]?crash|[_ -]?failure)\b",
    r"\bsubsys(?:tem)?(?:[_ -]?restart|[_ -]?crash)\b",
    r"\bSSR\b.*\bmodem\b",
    r"\bFatal error on the modem\b",
    r"\bmodem ramdump\b",
    r"\bramdump\b.*\bmodem\b",
    r"\bQualcomm CrashDump\b",
    r"\bCrashDump Mode\b",
    r"\bSOC crashed\b",
    r"\bUnable to wake SOC\b",
    r"\bqcril\b.*\bcrash\b",
    r"\brild\b.*\bcrash\b",
    r"\bvendor\.ril\b.*\bcrash\b",
    r"\bmodem exception\b",
    r"\bMD(?:1|3)?\s+exception\b",
    r"\bMD_EX\b",
    r"\b(CCCI|EEMCS|ECCCI)\b.*\b(exception|assert|fatal|crash|reset)\b",
    r"\b(md1|md3|modem)\b.*\b(exception|assert|fatal|crash|reset)\b",
    r"\baee\b.*\b(md1|md3|modem|ccci)\b",
]

IGNORE_PATTERNS = [
    r"\bRemove all retry and throttling entries,\s*reason=MODEM_RESTART\b",
    r"\bEVENT_MD_DATA_RETRY_COUNT_RESET\b",
    r"\bRIL_UNSOL_MD_DATA_RETRY_COUNT_RESET\b",
]

ONEPLUS_PATTERNS = [
    r"\bQUALCOMM CrashDump Mode\b",
    r"\bOnePlusLogKit\b",
    r"\boemlogkit\b",
    r"\bsubsys-restart:.*modem\b",
    r"\brestart_level_related\b.*modem\b",
    r"\bmtk[-_ ]?modem[-_ ]?daemon\b.*\b(crash|died|fatal|exception|restart)\b",
    r"\bemdlogger\b.*\b(modem|md1|exception|crash)\b",
    r"\bccci_fsm\b.*\b(exception|crash|reset|assert)\b",
]

PIXEL_PATTERNS = [
    r"\bmodem_ssr\b",
    r"\bPixelStats\b.*\bmodem\b",
    r"\bvendor\.google\.radio\b.*\bcrash\b",
    r"\bExynosModem\b.*\b(crash|reset|panic)\b",
    r"\bmodem.*\bSSR_REASON\b",
    r"\bSTATE_CRASH_EXIT\b",
    r"\bMODEM STATUS\b.*\bSTATE_(CRASH_EXIT|BOOTING)\b",
    r"\bCrash by CP\b",
]

DEFAULT_RAW_LOG_FILTER = (
    r"subsystemrestart|crashinfo_modem|crash_exit|crash by cp|cp crash|"
    r"modem.*(crash|reset|assert|fatal|panic|failure)|"
    r"(crash|reset|assert|fatal|panic|failure).*modem|"
    r"STATE_(CRASH_EXIT|BOOTING)|MODEM STATUS|"
    r"RADIO_NOT_AVAILABLE|AIRPLANE_MODE|Airplane mode|airplaneMode=(true|false)|"
    r"cpif|\bSSR\b"
)


STOP_REQUESTED = False


def build_patterns(profile: str, extra_patterns: Iterable[str]) -> list[re.Pattern[str]]:
    patterns = list(COMMON_PATTERNS)
    if profile in {"oneplus", "all"}:
        patterns.extend(ONEPLUS_PATTERNS)
    if profile in {"pixel", "all"}:
        patterns.extend(PIXEL_PATTERNS)
    patterns.extend(extra_patterns)
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


def build_ignore_patterns() -> list[re.Pattern[str]]:
    return [re.compile(pattern, re.IGNORECASE) for pattern in IGNORE_PATTERNS]


def adb_command(adb: str, device: str | None, args: list[str]) -> list[str]:
    command = [adb]
    if device:
        command.extend(["-s", device])
    command.extend(args)
    return command


def run_checked(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(f"Command failed ({exc.returncode}): {' '.join(command)}") from exc


def list_devices(adb: str) -> int:
    result = subprocess.run([adb, "devices", "-l"], text=True, capture_output=True)
    sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.returncode


def now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).astimezone().isoformat(timespec="seconds")


def now_stamp() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def sanitize_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "unknown"


def run_capture(command: list[str], timeout: float = 15.0) -> str:
    try:
        result = subprocess.run(
            command,
            text=True,
            capture_output=True,
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        return f"{stdout}\n{stderr}\n[TIMEOUT after {timeout}s]\n"
    output = result.stdout or ""
    if result.stderr:
        output += "\n[stderr]\n" + result.stderr
    if result.returncode != 0:
        output += f"\n[exit_code={result.returncode}]\n"
    return output


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", errors="replace")


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def adb_shell(args: argparse.Namespace, command: str, *, root: bool = False, timeout: float = 15.0) -> str:
    shell_command = ["shell"]
    if root:
        shell_command.extend(["su", "-c", command])
    else:
        shell_command.append(command)
    return run_capture(adb_command(args.adb, args.device, shell_command), timeout=timeout)


def default_session_dir(args: argparse.Namespace) -> Path | None:
    if args.session_dir:
        return Path(args.session_dir).expanduser()
    if args.device_type == "Pixel8":
        serial = sanitize_name(args.device or "default")
        return Path("logs") / "baseband_monitor" / f"{now_stamp()}_Pixel8_{serial}"
    return None


def setup_session(args: argparse.Namespace) -> None:
    session_dir = default_session_dir(args)
    args.session_path = session_dir
    if session_dir is None:
        return
    session_dir.mkdir(parents=True, exist_ok=True)
    if not args.output:
        args.output = str(session_dir / "baseband_crashes.jsonl")
    if not args.raw_log:
        args.raw_log = str(session_dir / "logcat_filtered.log")
    manifest = {
        "created_at": now_iso(),
        "adb": args.adb,
        "adb_serial": args.device,
        "profile": args.profile,
        "device_type": args.device_type,
        "buffers": args.buffers,
        "format": args.format,
        "event_log": args.output,
        "raw_log": args.raw_log,
        "raw_log_mode": args.raw_log_mode,
        "raw_log_filter": args.raw_log_filter,
    }
    write_text(session_dir / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")


def capture_pixel8_evidence(args: argparse.Namespace, reason: str, event: dict | None = None) -> None:
    session_dir: Path | None = getattr(args, "session_path", None)
    if session_dir is None or args.device_type != "Pixel8":
        return

    evidence_dir = session_dir / f"evidence_{now_stamp()}_{sanitize_name(reason)}"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    if event is not None:
        write_text(evidence_dir / "trigger_event.json", json.dumps(event, ensure_ascii=False, indent=2) + "\n")

    write_text(evidence_dir / "adb_devices.txt", run_capture([args.adb, "devices", "-l"]))
    write_text(
        evidence_dir / "props.txt",
        adb_shell(
            args,
            "getprop ro.product.device; getprop ro.boot.hardware; "
            "getprop ro.boot.hardware.platform; getprop ro.build.fingerprint; "
            "getprop gsm.version.baseband",
        ),
    )
    write_text(evidence_dir / "uptime.txt", adb_shell(args, "cat /proc/uptime"))
    write_text(
        evidence_dir / "telephony_registry.txt",
        adb_shell(args, "dumpsys telephony.registry", timeout=25.0),
    )
    write_text(
        evidence_dir / "radio_modem_services.txt",
        adb_shell(args, 'getprop | grep -Ei "init\\.svc.*(cbd|modem|radio|ril)"', timeout=10.0),
    )
    write_text(
        evidence_dir / "radio_modem_processes.txt",
        adb_shell(args, 'ps -A | grep -Ei "cbd|modem_svc|radio|rild|phone|ssr|sit"', timeout=10.0),
    )
    write_text(
        evidence_dir / "dropbox_modem.txt",
        adb_shell(
            args,
            'dumpsys dropbox --print | grep -Ei "SubsystemRestart|STATE_CRASH_EXIT|CP Crash|Crash by CP|modem|SSR|CRASH_EXIT" | tail -n 200',
            timeout=40.0,
        ),
    )
    write_text(
        evidence_dir / "pixel8_vendor_modem_root.txt",
        adb_shell(
            args,
            r'''
echo "===== /data/vendor/modem_stat/debug.txt ====="
cat /data/vendor/modem_stat/debug.txt 2>/dev/null || echo NO_MODEM_STAT
echo "===== /data/vendor/ssrdump ====="
ls -lt /data/vendor/ssrdump 2>/dev/null || echo NO_SSRDUMP_DIR
echo "===== crashinfo_modem files ====="
for f in /data/vendor/ssrdump/crashinfo_modem*; do
  [ -e "$f" ] || continue
  echo "----- $f -----"
  ls -l "$f"
  cat "$f"
done
echo "===== /dev/logbuffer_cpif tail ====="
timeout 3 cat /dev/logbuffer_cpif 2>/dev/null | tail -n 300 || true
echo "===== pcie_event_stats ====="
cat /sys/devices/platform/cpif/modem/pcie_event_stats 2>/dev/null || echo NO_PCIE_EVENT_STATS
echo "===== vendor radio/log dirs ====="
ls -lt /data/vendor/radio/sit-ril 2>/dev/null | head -n 80 || true
ls -lt /data/vendor/radio/logs/always-on 2>/dev/null | head -n 80 || true
ls -lt /data/vendor/slog 2>/dev/null | head -n 80 || true
ls -lt /data/vendor/log/cbd 2>/dev/null | head -n 80 || true
''',
            root=True,
            timeout=40.0,
        ),
    )
    write_text(
        evidence_dir / "logcat_snapshot_filtered.txt",
        adb_shell(
            args,
            'logcat -d -v threadtime -b all | grep -Ei "SubsystemRestart|STATE_CRASH_EXIT|MODEM STATUS|CP Crash|Crash by CP|modem|SSR|RADIO_NOT_AVAILABLE|radio power|airplane|cpif" | tail -n 500',
            timeout=40.0,
        ),
    )

    if not args.quiet:
        print(f"[info] Pixel8 evidence saved: {evidence_dir}")
        sys.stdout.flush()


def emit_event(
    line: str,
    matched_pattern: str,
    log_file: Path | None,
    raw_context: list[str],
    quiet: bool,
) -> dict:
    event = {
        "time": now_iso(),
        "type": "baseband_crash_suspected",
        "matched_pattern": matched_pattern,
        "line": line.rstrip("\n"),
        "recent_context": raw_context[-20:],
    }
    if not quiet:
        print("\n[BASEBAND-CRASH-SUSPECTED]")
        print(json.dumps(event, ensure_ascii=False, indent=2))
        sys.stdout.flush()
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        with log_file.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def stream_logcat(args: argparse.Namespace) -> int:
    global STOP_REQUESTED
    setup_session(args)
    patterns = build_patterns(args.profile, args.pattern)
    ignore_patterns = build_ignore_patterns()
    log_file = Path(args.output).expanduser() if args.output else None
    raw_log_file = Path(args.raw_log).expanduser() if args.raw_log else None
    raw_log_filter = re.compile(args.raw_log_filter, re.IGNORECASE) if args.raw_log_filter else None
    recent_lines: list[str] = []
    last_event_time = 0.0

    if args.clear:
        run_checked(adb_command(args.adb, args.device, ["logcat", "-c"]))

    command = adb_command(
        args.adb,
        args.device,
        ["logcat", "-v", args.format, "-b", args.buffers],
    )
    if args.filter:
        command.append(args.filter)

    if not args.quiet:
        print(f"[info] profile={args.profile}")
        print(f"[info] command={' '.join(command)}")
        print(f"[info] patterns={len(patterns)}")
        if getattr(args, "session_path", None) is not None:
            print(f"[info] session={args.session_path}")
        if log_file is not None:
            print(f"[info] event log={log_file}")
        if raw_log_file is not None:
            print(f"[info] raw log={raw_log_file}")
        print("[info] monitoring started; press Ctrl+C to stop")
        sys.stdout.flush()

    if args.capture_start and args.device_type == "Pixel8":
        capture_pixel8_evidence(args, "start")

    proc: subprocess.Popen | None = None

    def finish(reason: str, return_code: int = 0) -> int:
        if proc is not None and proc.poll() is None:
            proc.send_signal(signal.SIGINT)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if args.capture_final and args.device_type == "Pixel8":
            capture_pixel8_evidence(args, reason)
        if not args.quiet:
            print("\n[info] monitoring stopped")
        return return_code

    while True:
        if STOP_REQUESTED:
            return finish("signal")
        proc = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            bufsize=1,
        )
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                if STOP_REQUESTED:
                    return finish("signal")
                if args.print_all:
                    print(line, end="")
                should_write_raw = (
                    raw_log_file is not None
                    and (args.raw_log_mode == "all" or raw_log_filter is None or raw_log_filter.search(line))
                )
                if should_write_raw:
                    raw_log_file.parent.mkdir(parents=True, exist_ok=True)
                    with raw_log_file.open("a", encoding="utf-8", errors="replace") as raw_out:
                        raw_out.write(line)
                recent_lines.append(line.rstrip("\n"))
                if len(recent_lines) > args.context_lines:
                    del recent_lines[: len(recent_lines) - args.context_lines]

                if any(pattern.search(line) for pattern in ignore_patterns):
                    continue

                for pattern in patterns:
                    if pattern.search(line):
                        current_time = time.monotonic()
                        if current_time - last_event_time >= args.debounce_seconds:
                            event = emit_event(line, pattern.pattern, log_file, recent_lines, args.quiet)
                            last_event_time = current_time
                            if args.capture_on_event and args.device_type == "Pixel8":
                                capture_pixel8_evidence(args, "event", event)
                        break
        except KeyboardInterrupt:
            return finish("final")

        return_code = proc.wait()
        if not args.reconnect:
            return finish(f"exit_{return_code}", return_code)
        if not args.quiet:
            print(f"[warn] adb logcat exited with code {return_code}; reconnecting in {args.reconnect_delay}s")
        time.sleep(args.reconnect_delay)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Monitor Android logcat for baseband/modem crash signals.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--adb", default=shutil.which("adb") or "adb", help="adb executable path")
    parser.add_argument("-s", "--device", help="ADB serial; omit when only one device is attached")
    parser.add_argument(
        "--device-type",
        choices=["generic", "Pixel8"],
        default="generic",
        help="Enable device-specific evidence capture. Pixel8 creates a per-run session directory.",
    )
    parser.add_argument(
        "--profile",
        choices=["oneplus", "pixel", "all"],
        default="all",
        help="Device-specific keyword preset",
    )
    parser.add_argument(
        "-b",
        "--buffers",
        default="radio,crash,system,kernel",
        help="Comma-separated logcat buffers",
    )
    parser.add_argument(
        "--format",
        default="threadtime",
        choices=["brief", "process", "tag", "thread", "raw", "time", "threadtime", "long"],
        help="logcat output format",
    )
    parser.add_argument("--filter", default="", help="Optional native logcat filter expression")
    parser.add_argument(
        "--pattern",
        action="append",
        default=[],
        help="Extra regex to treat as a crash signal; can be passed multiple times",
    )
    parser.add_argument("-o", "--output", help="Append crash events as JSONL to this file")
    parser.add_argument(
        "--session-dir",
        help="Directory for this run's manifest, raw logcat, event JSONL, and pulled device evidence.",
    )
    parser.add_argument("--raw-log", help="Write all monitored logcat lines to this file")
    parser.add_argument(
        "--raw-log-mode",
        choices=["filtered", "all"],
        default="filtered",
        help="Write only modem/radio-related logcat lines by default; use all for every monitored line.",
    )
    parser.add_argument(
        "--raw-log-filter",
        default=DEFAULT_RAW_LOG_FILTER,
        help="Regex used when --raw-log-mode=filtered.",
    )
    parser.add_argument(
        "--capture-start",
        action="store_true",
        help="Capture device evidence immediately when monitoring starts.",
    )
    parser.add_argument(
        "--no-capture-on-event",
        dest="capture_on_event",
        action="store_false",
        help="Do not pull device evidence when a crash-like event is detected.",
    )
    parser.add_argument(
        "--no-capture-final",
        dest="capture_final",
        action="store_false",
        help="Do not pull device evidence when the monitor exits.",
    )
    parser.add_argument("--quiet", action="store_true", help="Do not print monitor status or crash events to stdout")
    parser.add_argument("--clear", action="store_true", help="Clear logcat before monitoring")
    parser.add_argument("--print-all", action="store_true", help="Also print every logcat line")
    parser.add_argument("--context-lines", type=int, default=80, help="Recent lines retained in each event")
    parser.add_argument("--debounce-seconds", type=float, default=10.0, help="Minimum seconds between events")
    parser.add_argument("--reconnect", action="store_true", help="Restart logcat if adb exits")
    parser.add_argument("--reconnect-delay", type=float, default=2.0, help="Delay before reconnecting")
    parser.add_argument("--list-devices", action="store_true", help="List ADB devices and exit")
    parser.set_defaults(capture_on_event=True, capture_final=True)
    args = parser.parse_args()
    if args.device_type == "Pixel8" and args.profile == "all":
        args.profile = "pixel"
    return args


def main() -> int:
    args = parse_args()
    if args.list_devices:
        return list_devices(args.adb)
    def request_stop(_signum: int, _frame: object) -> None:
        global STOP_REQUESTED
        STOP_REQUESTED = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    return stream_logcat(args)


if __name__ == "__main__":
    raise SystemExit(main())
