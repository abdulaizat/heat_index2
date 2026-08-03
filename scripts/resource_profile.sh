#!/usr/bin/env bash
set -euo pipefail

phase="${1:-session}"
timestamp="$(date -Iseconds)"
cpu_count="$(nproc)"
mem_available_kib="$(awk '/MemAvailable/ {print $2}' /proc/meminfo)"
mem_available_gib="$(awk -v kib="$mem_available_kib" 'BEGIN { printf "%.1f", kib / 1024 / 1024 }')"
ram_status="ok"

if (( mem_available_kib < 12 * 1024 * 1024 )); then
  ram_status="below_target_headroom"
fi

echo "[resource_profile] phase=${phase} time=${timestamp}"
echo "[resource_profile] cpu_count=${cpu_count}"
echo "[resource_profile] mem_available_gib=${mem_available_gib}"
echo "[resource_profile] recommended_ram_headroom_gib=10-12"
echo "[resource_profile] ram_headroom_status=${ram_status}"
echo "[resource_profile] io_worker_cap=3"
echo "[resource_profile] cwd_disk:"
df -h . | awk 'NR<=2 {print}'

if [ -d /mnt/AizatDrive ]; then
  echo "[resource_profile] /mnt/AizatDrive disk:"
  df -h /mnt/AizatDrive | awk 'NR<=2 {print}'
fi
