#!/data/data/com.termux/files/usr/bin/bash
# Paper Minecraft (Java Edition) server for Termux, 2 GB heap
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$SRC/panel.py" ]] || { echo "ERROR: panel.py is missing" >&2; exit 1; }

DIR="${MC_DIR:-$HOME/mcserver}"
MC_VERSION="${MC_VERSION:-latest}"
API="https://fill.papermc.io/v3/projects/paper"
# Change YOUR_USERNAME: PaperMC asks for a User-Agent that identifies your script
UA="termux-mc-server/1.0 (https://github.com/YOUR_USERNAME/termux-mc-server)"

die() { echo "ERROR: $*" >&2; exit 1; }
fetch() { curl -fsSL --retry 3 -H "User-Agent: $UA" "$@"; }

[[ "${PREFIX:-}" == *com.termux* ]] || die "Run this inside Termux."
case "$(uname -m)" in
  aarch64|x86_64) ;;
  *) die "A 64-bit device is required for a 2 GB Java heap." ;;
esac

total_mb=$(awk '/MemTotal/ {print int($2/1024)}' /proc/meminfo)
if (( total_mb < 3500 )); then
  echo "WARNING: ${total_mb} MB total RAM. Android may kill a 2 GB server."
fi

echo "==> Installing packages"
pkg update -y
pkg upgrade -y
pkg install -y curl jq coreutils tmux python
if ! pkg install -y openjdk-25; then
  echo "==> Trying the Termux User Repository"
  pkg install -y tur-repo
  pkg update -y
  pkg install -y openjdk-25 || die "Could not install openjdk-25."
fi
java -version 2>&1 | grep -q 'version "25' \
  || die "Java 25 is not the active Java. Check with: java -version"

mkdir -p "$DIR"
cd "$DIR"

echo "==> Finding a stable Paper build"
if [[ "$MC_VERSION" == "latest" ]]; then
  versions=$(fetch "$API" | jq -r '.versions | to_entries[] | .value[]' | grep -v -- '-')
else
  versions="$MC_VERSION"
fi

build=""
for v in $versions; do
  build=$(fetch "$API/versions/$v/builds" \
    | jq -c 'map(select(.channel == "STABLE")) | max_by(.id) // empty')
  if [[ -n "$build" ]]; then MC_VERSION="$v"; break; fi
done
[[ -n "$build" ]] || die "No stable Paper build found."
[[ "$MC_VERSION" == 26.* ]] || die "This script supports Minecraft 26.x only (found $MC_VERSION)."

url=$(jq -r '.downloads."server:default".url' <<<"$build")
sha=$(jq -r '.downloads."server:default".checksums.sha256' <<<"$build")

echo "==> Downloading Paper $MC_VERSION"
fetch -o server.jar.part "$url"
echo "$sha  server.jar.part" | sha256sum -c - || die "Checksum mismatch."
mv server.jar.part server.jar

if ! grep -qx 'eula=true' eula.txt 2>/dev/null; then
  echo "Read the Minecraft EULA: https://aka.ms/MinecraftEULA"
  read -rp "Type 'yes' if you agree: " answer
  [[ "$answer" == "yes" ]] || die "You must accept the EULA to run a server."
  echo "eula=true" > eula.txt
fi

if [[ ! -f server.properties ]]; then
  cat > server.properties <<'EOF'
motd=My Termux Server
server-port=25565
max-players=5
view-distance=6
simulation-distance=4
online-mode=true
EOF
fi

cat > start.sh <<'EOF'
#!/data/data/com.termux/files/usr/bin/bash
cd "$(dirname "$0")" || exit 1
command -v termux-wake-lock >/dev/null && termux-wake-lock
trap 'command -v termux-wake-unlock >/dev/null && termux-wake-unlock' EXIT

# Runs the server (2 GB heap) together with the web panel
python panel.py
EOF
chmod +x start.sh
cp "$SRC/panel.py" panel.py

echo
echo "Done. Start with:  $DIR/start.sh"
echo "The panel link prints when it starts. Type 'link' to show it again."
echo "To quit: type 'stop', then press Ctrl+C."
