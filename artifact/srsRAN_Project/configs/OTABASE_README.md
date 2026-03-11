# OTABase 5G RRC Fuzzing — Quick Start

## Prerequisites

1. **Build srsRAN_Project** with OTABase modifications:

```bash
cd artifact/srsRAN_Project
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j$(nproc) gnb
```

2. **Prepare test payloads**.  Use the test-case-generator to produce payload
   files (e.g. `rrcPayloads1`, `rrcPayloads2`, …).  Each file has the format:

```
<total_line_count>
<numbering>,<hex_payload>,<msgName>,<fieldName>
...
```

3. **Create the index file** (`testFileIndex` by default):

```bash
echo "rrcPayloads1" > testFileIndex
```

   Optionally specify a starting line: `echo "rrcPayloads1,1,0" > testFileIndex`

## Running

```bash
# Single-binary gNB with USRP B200, band n78, 20 MHz + OTABase fuzzing
sudo ./gnb -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
           -c ../configs/otabase_fuzzing.yml
```

Or pass OTABase options directly via CLI:

```bash
sudo ./gnb -c ../configs/gnb_rf_b200_tdd_n78_20mhz.yml \
    --otabase_enable_5g_rrc_fuzzing true \
    --otabase_test_index_file testFileIndex \
    --otabase_check_period 10 \
    --otabase_replay_mode false
```

## Configuration Reference

| YAML Key | CLI Flag | Default | Description |
|---|---|---|---|
| `cu_cp.rrc.otabase_enable_5g_rrc_fuzzing` | `--otabase_enable_5g_rrc_fuzzing` | `false` | Master switch for OTABase RRC fuzzing |
| `cu_cp.rrc.otabase_test_index_file` | `--otabase_test_index_file` | `testFileIndex` | Path to the index file |
| `cu_cp.rrc.otabase_check_period` | `--otabase_check_period` | `10` | Oracle liveness check period (messages) |
| `cu_cp.rrc.otabase_replay_mode` | `--otabase_replay_mode` | `false` | Enable replay mode (shorter check period, no blacklisting) |

## How It Works

1. **Injection**: After each UL DCCH response (setup complete, security mode
   complete, UE cap info, reconfig complete, reestablishment complete), the gNB
   reads the next hex payload from the test file and sends it as a raw DL DCCH
   PDU on SRB1.

2. **Oracle**: Every `check_period` messages, a UECapabilityEnquiry is sent
   instead of a test payload.  A 1-second timer starts.  If the UE responds,
   testing continues.  If not, up to 2 retries are attempted before entering
   backtracking mode.

3. **Backtracking**: The last 10 test messages are replayed newest-first,
   alternating each with an oracle check.  The message that triggers the oracle
   failure is identified as the crash candidate and saved to
   `otabase_crashes/crashes/crash_N/candidates.json`.

4. **Blacklisting**: After identifying a crash candidate, messages with the
   same `msgName+fieldName` are skipped in the current test file to avoid
   repeatedly sending the same crashing pattern.  Temporary blacklisting tracks
   counts across messages and auto-resets after 30 occurrences.
