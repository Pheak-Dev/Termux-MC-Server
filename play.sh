#!/data/data/com.termux/files/usr/bin/bash
# Start the playit tunnel and the Minecraft server together
PLAYIT="$HOME/.playit"
SERVER="${MC_DIR:-$HOME/mcserver}/start.sh"
pid=""

command -v playitd >/dev/null || { echo "ERROR: playit is not installed"; exit 1; }
[[ -f "$SERVER" ]] || { echo "ERROR: run setup.sh first"; exit 1; }
mkdir -p "$PLAYIT" && chmod 700 "$PLAYIT"

cleanup() {
  [[ -n "$pid" ]] && kill "$pid" 2>/dev/null
}
trap cleanup EXIT

if pgrep -x playitd >/dev/null; then
  echo "playitd is already running."
else
  playitd --socket-path "$PLAYIT/playitd.sock" \
          --secret-path "$PLAYIT/playit.toml" > "$PLAYIT/playitd.log" 2>&1 &
  pid=$!
  sleep 3
  if ! kill -0 "$pid" 2>/dev/null; then
    echo "ERROR: playitd stopped. See $PLAYIT/playitd.log"
    exit 1
  fi
  echo "playitd started. Log: $PLAYIT/playitd.log"
fi

bash "$SERVER"
