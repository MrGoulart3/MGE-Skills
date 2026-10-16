#!/usr/bin/env bash
# doctor.sh - check (never install) what molecular-motion-video needs.
# Verifica (nunca instala) o que a skill precisa.
# Env: MIN_DISK_GB=20 MIN_RAM_GB=8 (planning thresholds; adapt to your project)
# Env: BLENDER=/path/to/blender  ENV_RENDER ENV_TTS ENV_CALC (env names; defaults mmv-render/mmv-tts/mmv-calc)
MIN_DISK_GB="${MIN_DISK_GB:-20}"
MIN_RAM_GB="${MIN_RAM_GB:-8}"
bad=0
ok(){ printf '  OK       %s\n' "$1"; }
miss(){ printf '  MISSING  %s\n' "$1"; bad=$((bad+1)); }
warn(){ printf '  WARN     %s\n' "$1"; }

echo "== molecular-motion-video doctor =="
echo "[Blender]"
B="${BLENDER:-$(command -v blender || true)}"
if [ -n "$B" ] && [ -x "$B" ]; then
  v=$("$B" --version 2>/dev/null | head -1)
  ok "blender: $v ($B)"
  case "$v" in *"Blender 4."*|*"Blender 5."*) ;; *) warn "Blender 4.2 LTS recommended";; esac
else miss "blender (set BLENDER=/path/to/blender or put it on PATH; see README)"; fi

echo "[ffmpeg]"
for t in ffmpeg ffprobe; do
  if command -v $t >/dev/null; then ok "$t: $($t -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
  else warn "$t not on PATH (may live inside the render env)"; fi
done

echo "[conda envs]"
RUN=""
if command -v conda >/dev/null; then RUN="conda run -n"; elif command -v micromamba >/dev/null; then RUN="micromamba run -n"; fi
if [ -z "$RUN" ]; then miss "conda or micromamba"; else
  chk(){ # name, python test
    if $RUN "$1" python -c "$2" >/dev/null 2>&1; then ok "env $1"; else miss "env $1 (or a package in it)"; fi; }
  chk "${ENV_RENDER:-mmv-render}" "import numpy,PIL,scipy,ase;assert int(PIL.__version__.split('.')[0])>=10"
  if $RUN "${ENV_RENDER:-mmv-render}" ffmpeg -version >/dev/null 2>&1; then ok "ffmpeg in render env"; else warn "ffmpeg not in render env"; fi
  chk "${ENV_TTS:-mmv-tts}" "import torch,chatterbox,faster_whisper"
  chk "${ENV_CALC:-mmv-calc}" "import openmm,tblite,ase,scipy"
fi

echo "[fonts]"
if command -v fc-list >/dev/null && fc-list 2>/dev/null | grep -qi "DejaVu\|Liberation\|Noto\|Manrope"; then
  ok "font family available (set FONT/SYMBOL_FONT for example post scripts)"
else miss "fonts (install DejaVu, Noto, Liberation or your preferred font)"; fi

echo "[resources]"
d=$(df -Pk . | awk 'NR==2{printf "%d",$4/1048576}')
[ "$d" -ge "$MIN_DISK_GB" ] && ok "free disk: ${d} GB" || miss "free disk: ${d} GB (< ${MIN_DISK_GB} GB)"
n=$(nproc 2>/dev/null || echo 1); ok "CPU threads: $n"
r=$(awk '/MemTotal/{printf "%d",$2/1048576}' /proc/meminfo 2>/dev/null || echo 0)
[ "$r" -ge "$MIN_RAM_GB" ] && ok "RAM: ${r} GB" || miss "RAM: ${r} GB (< ${MIN_RAM_GB} GB)"

echo
if [ $bad -eq 0 ]; then echo "Summary: all OK"; exit 0; else echo "Summary: $bad item(s) MISSING / itens faltando"; exit 1; fi
