#!/usr/bin/env bash
# Best-effort cleanup for an interrupted E5 run. Targets only E5 tier scripts,
# E5 configs, the dedicated broker and the shared E4 simulation processes.
set -u

PI_HOST="${PI_HOST:-shikai@shikai-pi.local}"
MAC_HOST="${MAC_HOST:-alex@Shikais-MBP.local}"

eval/e4/cleanup.sh --quiet 2>/dev/null || true

pkill -TERM -f '[e]val/e5/dds_probe.py' 2>/dev/null || true
pkill -TERM -f '[e]val/common/ps_proc_sampler.py.*eval/e5/results/' 2>/dev/null || true

ssh -o BatchMode=yes -o ConnectTimeout=5 "$PI_HOST" \
  "pkill -TERM -f '[e]val/e5/pi_tier.sh' 2>/dev/null || true; \
   pkill -INT -f '[m]onitor/monitor_node.py -c eval/e5/results/' 2>/dev/null || true; \
   pkill -INT -f '[m]onitor/node_runner.py -c eval/e5/results/.*/config/pi_reference.yaml' 2>/dev/null || true; \
   pkill -TERM -f '[m]osquitto -c eval/e5/mosquitto.conf' 2>/dev/null || true" \
  2>/dev/null || true

ssh -o BatchMode=yes -o ConnectTimeout=5 "$MAC_HOST" \
  "pkill -TERM -f '[e]val/e5/mac_tier.sh' 2>/dev/null || true; \
   pkill -INT -f '[m]onitor/node_runner.py -c eval/e5/results/.*/config/mac.yaml' 2>/dev/null || true; \
   pkill -TERM -f '[e]val/common/ps_proc_sampler.py.*eval/e5/results/' 2>/dev/null || true" \
  2>/dev/null || true

echo "E5 cleanup requested on PC, Pi, and Mac"

