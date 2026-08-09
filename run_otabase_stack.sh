#!/usr/bin/env bash
#
# OTABase 4G RRC fuzzing helper.
#
# 使用前先创建/选择一个 session；epc、enb、monitor 不会在缺少 session 时
# 自动创建目录。
#
#   cd /home/nanfeng/projects/OTABaseMine
#   ./run_otabase_stack.sh new-session
#
# 三个终端分开启动：
#   cd /home/nanfeng/projects/OTABaseMine
#   ./run_otabase_stack.sh epc
#   EARFCN=2452 TEST_DEVICE=Pixel8 ./run_otabase_stack.sh enb
#   ./run_otabase_stack.sh monitor
#
# 查看当前会执行的完整命令：
#   ./run_otabase_stack.sh print
#
# 推荐的 Pixel 8 三终端运行方式。三个进程都由本脚本启动，并共用同一个
# SESSION_DIR，抓包、监控日志和手机侧证据会归档到同一个目录。
#
#   ./run_otabase_stack.sh new-session
#
#   # 终端 1
#   ./run_otabase_stack.sh epc
#
#   # 终端 2
#   EARFCN=2452 TEST_DEVICE=Pixel8 ./run_otabase_stack.sh enb
#
#   # 终端 3
#   ./run_otabase_stack.sh monitor
#
# 如果想结束后忘记当前 session：
#   ./run_otabase_stack.sh clear-session
#
# session 目录内会保存：
#   epc_s1ap.pcap
#   enb_s1ap.pcap
#   enb_mac.pcap
#   monitor.log
#   logcat_filtered.log
#   baseband_crashes.jsonl
#   otabase_epc_crashes/
#   otabase_rrc_crashes/
#   evidence_*_event/
#   evidence_*_final/
#
# 可覆盖的环境变量：
#   ADB_SERIAL=38251FDJH00DP5
#   EARFCN=2452
#   TEST_DEVICE=Pixel8
#   SESSION_DIR=/path/to/session
#   EPC_OUTPUT=/path/to/session/otabase_epc_crashes
#   RRC_OUTPUT=/path/to/session/otabase_rrc_crashes
#   MONITOR_OUTPUT=/path/to/session/baseband_crashes.jsonl
#   EPC_PCAP=/path/to/session/epc_s1ap.pcap
#   ENB_MAC_PCAP=/path/to/session/enb_mac.pcap
#   ENB_S1AP_PCAP=/path/to/session/enb_s1ap.pcap
set -euo pipefail

ROOT_DIR="/home/nanfeng/projects/OTABaseMine"
EPC_DIR="$ROOT_DIR/artifact/otabase/build/srsepc/src"
ENB_DIR="$ROOT_DIR/artifact/otabase/build/srsenb/src"
CURRENT_SESSION_FILE="$ROOT_DIR/logs/baseband_monitor/current_session"
COMMAND="${1:-}"
ADB_SERIAL="${ADB_SERIAL:-38251FDJH00DP5}"
EARFCN="${EARFCN:-2452}"
TEST_DEVICE="${TEST_DEVICE:-Pixel8}"
DEVICE_TYPE="${DEVICE_TYPE:-Pixel8}"
MONITOR_PROFILE="${MONITOR_PROFILE:-pixel}"
SESSION_DIR="${SESSION_DIR:-}"

session_path() {
  local serial
  serial="$(printf '%s' "$ADB_SERIAL" | tr -c '[:alnum:]_.-' '_')"
  printf '%s/logs/baseband_monitor/%s_Pixel8_%s\n' "$ROOT_DIR" "$(date +%Y%m%d_%H%M%S)" "$serial"
}

create_session() {
  local path
  path="$(session_path)"
  mkdir -p "$path" "$(dirname "$CURRENT_SESSION_FILE")"
  printf '%s\n' "$path" >"$CURRENT_SESSION_FILE"
  printf '%s\n' "$path"
}

if [[ -z "$SESSION_DIR" && "$COMMAND" =~ ^(epc|enb|monitor|print)$ && -f "$CURRENT_SESSION_FILE" ]]; then
  SESSION_DIR="$(<"$CURRENT_SESSION_FILE")"
fi

if [[ -n "$SESSION_DIR" && "$SESSION_DIR" != /* ]]; then
  SESSION_DIR="$ROOT_DIR/$SESSION_DIR"
fi

if [[ -n "$SESSION_DIR" ]]; then
  EPC_OUTPUT="${EPC_OUTPUT:-$SESSION_DIR/otabase_epc_crashes}"
  RRC_OUTPUT="${RRC_OUTPUT:-$SESSION_DIR/otabase_rrc_crashes/rrc}"
  MONITOR_OUTPUT="${MONITOR_OUTPUT:-$SESSION_DIR/baseband_crashes.jsonl}"
  RAW_LOG_OUTPUT="${RAW_LOG_OUTPUT:-$SESSION_DIR/logcat_filtered.log}"
  EPC_PCAP="${EPC_PCAP:-$SESSION_DIR/epc_s1ap.pcap}"
  ENB_MAC_PCAP="${ENB_MAC_PCAP:-$SESSION_DIR/enb_mac.pcap}"
  ENB_S1AP_PCAP="${ENB_S1AP_PCAP:-$SESSION_DIR/enb_s1ap.pcap}"
else
  EPC_OUTPUT="${EPC_OUTPUT:-$ROOT_DIR/logs/otabase_epc_crashes}"
  RRC_OUTPUT="${RRC_OUTPUT:-$ROOT_DIR/logs/otabase_rrc_crashes}"
  MONITOR_OUTPUT="${MONITOR_OUTPUT:-$ROOT_DIR/logs/baseband_crashes.jsonl}"
  RAW_LOG_OUTPUT="${RAW_LOG_OUTPUT:-}"
  EPC_PCAP="${EPC_PCAP:-$EPC_DIR/epc.pcap}"
  ENB_MAC_PCAP="${ENB_MAC_PCAP:-$ENB_DIR/enb_mac.pcap}"
  ENB_S1AP_PCAP="${ENB_S1AP_PCAP:-$ENB_DIR/enb_s1ap.pcap}"
fi

mkdir -p \
  "$EPC_OUTPUT" \
  "$(dirname "$RRC_OUTPUT")" \
  "$(dirname "$MONITOR_OUTPUT")" \
  "$(dirname "$EPC_PCAP")" \
  "$(dirname "$ENB_MAC_PCAP")" \
  "$(dirname "$ENB_S1AP_PCAP")" \
  "$ROOT_DIR/logs"
if [[ -n "$SESSION_DIR" ]]; then
  mkdir -p "$SESSION_DIR"
fi

log_to_session() {
  local name="$1"
  if [[ -n "$SESSION_DIR" ]]; then
    mkdir -p "$SESSION_DIR"
    exec > >(tee -a "$SESSION_DIR/$name.log") 2>&1
    printf '[%s] SESSION_DIR=%s\n' "$(date '+%F %T')" "$SESSION_DIR"
  fi
}

require_session() {
  if [[ -z "$SESSION_DIR" ]]; then
    cat >&2 <<EOF
Error: SESSION_DIR is not set.

Please create/select a session first:
  ./run_otabase_stack.sh new-session

Then run this command again.
EOF
    exit 2
  fi
}

print_usage() {
  cat <<EOF
Usage:
  $0 epc       # run srsepc
  $0 enb       # run srsenb on EARFCN=$EARFCN
  $0 monitor   # run adb baseband crash monitor
  $0 new-session # create and remember a new SESSION_DIR
  $0 clear-session # forget the remembered SESSION_DIR
  $0 print     # print all commands

Environment overrides:
  ADB_SERIAL=$ADB_SERIAL
  EARFCN=$EARFCN
  TEST_DEVICE=$TEST_DEVICE
  DEVICE_TYPE=$DEVICE_TYPE
  MONITOR_PROFILE=$MONITOR_PROFILE
  SESSION_DIR=$SESSION_DIR
  EPC_OUTPUT=$EPC_OUTPUT
  RRC_OUTPUT=$RRC_OUTPUT
  MONITOR_OUTPUT=$MONITOR_OUTPUT
  EPC_PCAP=$EPC_PCAP
  ENB_MAC_PCAP=$ENB_MAC_PCAP
  ENB_S1AP_PCAP=$ENB_S1AP_PCAP
EOF
}

print_commands() {
  cat <<EOF
# EPC
SESSION_DIR="$SESSION_DIR"
cd "$EPC_DIR"
sudo ./srsepc ../../../conf/epc/epc.conf \\
  --test_state=1 \\
  --o=$EPC_OUTPUT \\
  --pcap.enable=true \\
  --pcap.filename=$EPC_PCAP

# eNB
SESSION_DIR="$SESSION_DIR" EARFCN=$EARFCN TEST_DEVICE=$TEST_DEVICE
cd "$ENB_DIR"
sudo ./srsenb ../../../conf/enb/enb.conf \\
  --target_protocol=rrc \\
  --o=$RRC_OUTPUT \\
  --rf.dl_earfcn=$EARFCN \\
  --test_device=$TEST_DEVICE \\
  --pcap.enable=true \\
  --pcap.filename=$ENB_MAC_PCAP \\
  --pcap.s1ap_enable=true \\
  --pcap.s1ap_filename=$ENB_S1AP_PCAP

# ADB baseband crash monitor
SESSION_DIR="$SESSION_DIR"
cd "$ROOT_DIR"
python3 adb_baseband_crash_monitor.py \\
  --device-type "$DEVICE_TYPE" \\
  --profile "$MONITOR_PROFILE" \\
  -s "$ADB_SERIAL" \\
  --clear \\
  --reconnect \\
  --quiet \\
  -o "$MONITOR_OUTPUT"$(if [[ -n "$RAW_LOG_OUTPUT" ]]; then printf ' \\\n  --raw-log "%s"' "$RAW_LOG_OUTPUT"; fi)$(if [[ -n "$SESSION_DIR" ]]; then printf ' \\\n  --session-dir "%s"' "$SESSION_DIR"; fi)
EOF
}

case "$COMMAND" in
  epc)
    require_session
    cd "$EPC_DIR"
    exec sudo ./srsepc ../../../conf/epc/epc.conf \
      --test_state=1 \
      --o="$EPC_OUTPUT" \
      --pcap.enable=true \
      --pcap.filename="$EPC_PCAP"
    ;;
  enb)
    require_session
    cd "$ENB_DIR"
    exec sudo ./srsenb ../../../conf/enb/enb.conf \
      --target_protocol=rrc \
      --o="$RRC_OUTPUT" \
      --rf.dl_earfcn="$EARFCN" \
      --test_device="$TEST_DEVICE" \
      --pcap.enable=true \
      --pcap.filename="$ENB_MAC_PCAP" \
      --pcap.s1ap_enable=true \
      --pcap.s1ap_filename="$ENB_S1AP_PCAP"
    ;;
  monitor)
    require_session
    log_to_session monitor
    cd "$ROOT_DIR"
    monitor_cmd=(
      python3 adb_baseband_crash_monitor.py
      --device-type "$DEVICE_TYPE"
      --profile "$MONITOR_PROFILE"
      -s "$ADB_SERIAL" \
      --clear \
      --reconnect \
      --quiet \
      -o "$MONITOR_OUTPUT"
    )
    if [[ -n "$RAW_LOG_OUTPUT" ]]; then
      monitor_cmd+=(--raw-log "$RAW_LOG_OUTPUT")
    fi
    if [[ -n "$SESSION_DIR" ]]; then
      monitor_cmd+=(--session-dir "$SESSION_DIR")
    fi
    exec "${monitor_cmd[@]}"
    ;;
  new-session)
    create_session
    ;;
  clear-session)
    rm -f "$CURRENT_SESSION_FILE"
    ;;
  print)
    print_commands
    ;;
  -h|--help|help|"")
    print_usage
    ;;
  *)
    echo "Unknown command: $1" >&2
    print_usage >&2
    exit 2
    ;;
esac
