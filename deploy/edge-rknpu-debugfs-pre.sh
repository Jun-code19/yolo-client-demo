#!/bin/sh
# 挂载 debugfs；若 edge 无法直接读 debugfs，则写入 /run/edge-ai-box/ 供 API 读取
RUN_DIR=/run/edge-ai-box
EDGE_GID=edge

mkdir -p "$RUN_DIR"
chmod 755 "$RUN_DIR" 2>/dev/null || true

if [ ! -d /sys/kernel/debug ]; then
  mount -t debugfs none /sys/kernel/debug 2>/dev/null || true
fi

for d in /sys/kernel/debug /sys/kernel/debug/rknpu; do
  if [ -d "$d" ]; then
    chmod a+rx "$d" 2>/dev/null || true
  fi
done

for f in /sys/kernel/debug/rknpu/load /sys/kernel/debug/rknpu/version; do
  if [ -f "$f" ]; then
    chmod a+r "$f" 2>/dev/null || true
  fi
done

publish() {
  src=$1
  dest=$2
  if [ ! -f "$src" ]; then
    return 0
  fi
  if cat "$src" > "$dest" 2>/dev/null; then
    chown "root:${EDGE_GID}" "$dest" 2>/dev/null || chown root:root "$dest" 2>/dev/null || true
    chmod 644 "$dest" 2>/dev/null || true
  fi
  return 0
}

publish /sys/kernel/debug/rknpu/load "$RUN_DIR/rknpu-load"
publish /sys/kernel/debug/rknpu/version "$RUN_DIR/rknpu-version"

exit 0
