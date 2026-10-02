#!/bin/sh
set -eu
cd "$(dirname "$0")"
exec ./bin/linux-x86_64/edgeai_chat models/instructions_v07/default.edge "$@"
