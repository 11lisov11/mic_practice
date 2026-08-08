#!/bin/sh
set -eu

if ss -ltn 2>/dev/null | grep -q ':2222 '; then
  exit 0
fi

exec /usr/sbin/sshd -D \
  -f /home/arduino/.ssh/sshd_config \
  -E /home/arduino/.ssh/sshd.log
