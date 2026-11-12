#!/usr/bin/env bash
#
# Provision a home server (Debian / Ubuntu / Raspberry Pi OS, amd64 or arm64)
# as the farm hub: Mosquitto + Home Assistant + Gate Monitor in Docker.
#
#   sudo ./scripts/provision-home-server.sh --lat 40.01 --lon -105.27 \
#        --ha-user farm --ha-password 'choose-one'
#
# Re-runnable: existing passwords, HA configuration and data are kept.
# Run with --help for all options.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# ----------------------------------------------------------------- defaults
INSTALL_DIR="/opt/farm-monitor"
TZ_NAME=""
LATITUDE=""
LONGITUDE=""
ELEVATION="0"
UNIT_SYSTEM="us_customary"
COUNTRY=""
EXTERNAL_BROKER=""
EXT_MQTT_USER=""
EXT_MQTT_PASSWORD=""
SIMULATE="true"
HA_VERSION="2026.11.1"
HA_USER=""
HA_PASSWORD=""
INSTALL_DOCKER="auto"
GATE_MONITOR_PORT="8000"
ASSUME_YES="false"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BOLD='\033[1m'; NC='\033[0m'
step() { echo -e "\n${YELLOW}==>${NC} ${BOLD}$*${NC}"; }
ok()   { echo -e "    ${GREEN}✓${NC} $*"; }
warn() { echo -e "    ${YELLOW}!${NC} $*"; }
die()  { echo -e "${RED}Error:${NC} $*" >&2; exit 1; }

usage() {
  cat <<EOF
Usage: sudo $0 [options]

Location (used for sunrise/sunset coop schedules and HA):
  --lat DEG               Latitude, e.g. 40.01
  --lon DEG               Longitude, e.g. -105.27 (west is negative)
  --elevation M           Elevation in metres (default 0)
  --tz ZONE               Time zone, e.g. America/Denver (default: host's)
  --metric                Use metric units in HA (default: US customary)
  --country CC            Two-letter country code for HA, e.g. US

Home Assistant:
  --ha-user NAME          Create/log in this HA owner and wire up MQTT automatically
  --ha-password PASS      Password for --ha-user (prompted if omitted)
  --ha-version VER        HA container version (default ${HA_VERSION})

MQTT broker:
  --external-broker H[:P] Use an existing broker instead of the bundled Mosquitto
  --mqtt-user U           Username on the external broker (optional)
  --mqtt-password P       Password on the external broker (optional)

Other:
  --dir PATH              Install location (default ${INSTALL_DIR})
  --port N                Gate Monitor web port (default ${GATE_MONITOR_PORT})
  --no-simulate           Don't run simulated coops/solar (use once real hardware reports)
  --skip-docker-install   Never install Docker (fail if missing)
  -y, --yes               Don't ask for confirmation
  -h, --help              This help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dir) INSTALL_DIR="$2"; shift 2 ;;
    --tz) TZ_NAME="$2"; shift 2 ;;
    --lat) LATITUDE="$2"; shift 2 ;;
    --lon) LONGITUDE="$2"; shift 2 ;;
    --elevation) ELEVATION="$2"; shift 2 ;;
    --metric) UNIT_SYSTEM="metric"; shift ;;
    --country) COUNTRY="${2^^}"; shift 2 ;;
    --external-broker) EXTERNAL_BROKER="$2"; shift 2 ;;
    --mqtt-user) EXT_MQTT_USER="$2"; shift 2 ;;
    --mqtt-password) EXT_MQTT_PASSWORD="$2"; shift 2 ;;
    --no-simulate) SIMULATE="false"; shift ;;
    --ha-version) HA_VERSION="$2"; shift 2 ;;
    --ha-user) HA_USER="$2"; shift 2 ;;
    --ha-password) HA_PASSWORD="$2"; shift 2 ;;
    --port) GATE_MONITOR_PORT="$2"; shift 2 ;;
    --skip-docker-install) INSTALL_DOCKER="never"; shift ;;
    -y|--yes) ASSUME_YES="true"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage; die "Unknown option: $1" ;;
  esac
done

num_re='^-?[0-9]+([.][0-9]+)?$'
[[ -z "$LATITUDE" || "$LATITUDE" =~ $num_re ]] || die "--lat must be a number"
[[ -z "$LONGITUDE" || "$LONGITUDE" =~ $num_re ]] || die "--lon must be a number"
[[ "$ELEVATION" =~ $num_re ]] || die "--elevation must be a number"
[[ -n "$LATITUDE" && -z "$LONGITUDE" || -z "$LATITUDE" && -n "$LONGITUDE" ]] && die "Give both --lat and --lon"
[[ "$GATE_MONITOR_PORT" =~ ^[0-9]+$ ]] || die "--port must be a number"
[[ -z "$COUNTRY" || "$COUNTRY" =~ ^[A-Z]{2}$ ]] || die "--country must be a two-letter code like US"

if [[ -z "$TZ_NAME" ]]; then
  TZ_NAME="$(timedatectl show -p Timezone --value 2>/dev/null || true)"
  [[ -z "$TZ_NAME" && -f /etc/timezone ]] && TZ_NAME="$(cat /etc/timezone)"
  TZ_NAME="${TZ_NAME:-UTC}"
fi

if [[ -n "$EXTERNAL_BROKER" ]]; then
  MQTT_HOST="${EXTERNAL_BROKER%%:*}"
  MQTT_PORT="${EXTERNAL_BROKER##*:}"
  [[ "$MQTT_PORT" == "$EXTERNAL_BROKER" ]] && MQTT_PORT=1883
else
  MQTT_HOST="127.0.0.1"
  MQTT_PORT="1883"
fi

# Root is needed to install Docker or write to a system path; a docker-group
# user can provision into a directory they own.
need_root="false"
if ! command -v docker >/dev/null 2>&1; then need_root="true"; fi
mkdir -p "$INSTALL_DIR" 2>/dev/null || need_root="true"
[[ -w "$INSTALL_DIR" ]] || need_root="true"
if [[ "$need_root" == "true" && $EUID -ne 0 ]]; then
  die "Run with sudo (needed to install Docker and/or write $INSTALL_DIR)"
fi

echo -e "${BOLD}Farm monitor home-server provisioning${NC}"
cat <<EOF
  Install dir     $INSTALL_DIR
  Time zone       $TZ_NAME
  Location        ${LATITUDE:-"(set during HA onboarding)"} ${LONGITUDE}
  MQTT broker     $([[ -n "$EXTERNAL_BROKER" ]] && echo "external $MQTT_HOST:$MQTT_PORT" || echo "bundled Mosquitto on :1883")
  Home Assistant  $HA_VERSION on :8123 $([[ -n "$HA_USER" ]] && echo "(auto-setup as '$HA_USER')")
  Gate Monitor    :$GATE_MONITOR_PORT (simulated coops/solar: $SIMULATE)
EOF
if [[ "$ASSUME_YES" != "true" && -t 0 ]]; then
  read -r -p "Continue? [Y/n] " reply
  [[ "$reply" =~ ^([yY]|)$ ]] || exit 1
fi

# --------------------------------------------------------- preflight: ports
port_in_use() { ss -Hltn "sport = :$1" 2>/dev/null | grep -q .; }
owned_by_stack() { docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$1"; }

step "Checking for conflicts"
if [[ -z "$EXTERNAL_BROKER" ]] && port_in_use 1883 && ! owned_by_stack mosquitto; then
  die "Port 1883 is already in use (a native mosquitto?). Either stop it:
      sudo systemctl disable --now mosquitto
  or reuse it with: --external-broker 127.0.0.1:1883"
fi
if port_in_use 8123 && ! owned_by_stack homeassistant; then
  die "Port 8123 is in use — is Home Assistant already installed on this host?"
fi
if port_in_use "$GATE_MONITOR_PORT" && ! owned_by_stack gate-monitor; then
  if systemctl is-active --quiet gate-monitor 2>/dev/null; then
    die "The old gate-monitor systemd service is using :$GATE_MONITOR_PORT. Stop it first:
      sudo systemctl disable --now gate-monitor"
  fi
  die "Port $GATE_MONITOR_PORT is in use; pick another with --port"
fi
ok "Ports free"

# ------------------------------------------------------------------ docker
install_docker() {
  . /etc/os-release
  local distro="$ID"
  case "$distro" in
    ubuntu|debian) ;;
    raspbian) distro="debian" ;;
    *) [[ "${ID_LIKE:-}" == *debian* ]] && distro="debian" || die "Unsupported distro '$ID'; install Docker manually and re-run with --skip-docker-install" ;;
  esac
  local codename="${VERSION_CODENAME:-}"
  [[ -n "${UBUNTU_CODENAME:-}" ]] && codename="$UBUNTU_CODENAME"
  [[ -n "$codename" ]] || die "Can't determine OS codename for the Docker repo"

  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg >/dev/null
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$distro/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$distro $codename stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
  systemctl enable --now docker
  if [[ -n "${SUDO_USER:-}" ]]; then
    usermod -aG docker "$SUDO_USER" && warn "Added $SUDO_USER to the docker group (log out/in to use docker without sudo)"
  fi
}

step "Docker"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  ok "$(docker --version)"
elif [[ "$INSTALL_DOCKER" == "never" ]]; then
  die "Docker with the compose plugin is required (--skip-docker-install given)"
else
  install_docker
  ok "Installed $(docker --version)"
fi

# ------------------------------------------------------------------- files
step "Installing files to $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"/{mosquitto,homeassistant/config/packages,homeassistant/config/dashboards}
cp "$REPO_DIR/deploy/docker-compose.yml" "$INSTALL_DIR/"
cp "$REPO_DIR/deploy/mosquitto/mosquitto.conf" "$INSTALL_DIR/mosquitto/"

# Server source for `docker compose build` (excluding dev artefacts).
rm -rf "${INSTALL_DIR:?}/server-src"
mkdir -p "$INSTALL_DIR/server-src"
tar -C "$REPO_DIR/server" \
  --exclude=.venv --exclude=node_modules --exclude=dist --exclude=data \
  --exclude=__pycache__ --exclude=.pytest_cache --exclude=.env \
  -cf - . | tar -C "$INSTALL_DIR/server-src" -xf -
ok "Compose file, broker config and server source"

HA_CFG="$INSTALL_DIR/homeassistant/config"
# configuration.yaml is the user's after first install; packages/dashboards are ours.
if [[ ! -f "$HA_CFG/configuration.yaml" ]]; then
  cp "$REPO_DIR/deploy/homeassistant/configuration.yaml" "$HA_CFG/"
  ok "HA configuration.yaml (new)"
else
  ok "HA configuration.yaml kept (already exists)"
fi
cp "$REPO_DIR/deploy/homeassistant/packages/"*.yaml "$HA_CFG/packages/"
cp "$REPO_DIR/deploy/homeassistant/dashboards/"*.yaml "$HA_CFG/dashboards/"
for f in automations.yaml; do [[ -f "$HA_CFG/$f" ]] || echo "[]" > "$HA_CFG/$f"; done
for f in scripts.yaml scenes.yaml; do [[ -f "$HA_CFG/$f" ]] || : > "$HA_CFG/$f"; done

{
  echo "# Managed by scripts/provision-home-server.sh — regenerated on each run."
  if [[ -n "$LATITUDE" ]]; then
    echo "name: Farm"
    echo "latitude: $LATITUDE"
    echo "longitude: $LONGITUDE"
    echo "elevation: $ELEVATION"
    echo "unit_system: $UNIT_SYSTEM"
    echo "time_zone: $TZ_NAME"
    [[ -n "$COUNTRY" ]] && echo "country: $COUNTRY"
  else
    echo "# No --lat/--lon given: HA uses the location chosen during onboarding."
  fi
  echo "packages: !include_dir_named packages"
} > "$HA_CFG/core.yaml"
ok "HA packages, dashboard and core.yaml"

# ------------------------------------------------------------- credentials
step "Credentials"
ENV_FILE="$INSTALL_DIR/.env"
touch "$ENV_FILE"; chmod 600 "$ENV_FILE"
env_get() { grep -E "^$1=" "$ENV_FILE" | tail -1 | cut -d= -f2- || true; }
env_set() {
  local key="$1" val="$2"
  if grep -qE "^$key=" "$ENV_FILE"; then
    sed -i "s|^$key=.*|$key=$val|" "$ENV_FILE"
  else
    echo "$key=$val" >> "$ENV_FILE"
  fi
}
gen_pw() { head -c 24 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24; }

if [[ -n "$EXTERNAL_BROKER" ]]; then
  env_set MQTT_SERVER_USER "$EXT_MQTT_USER"
  env_set MQTT_SERVER_PASSWORD "$EXT_MQTT_PASSWORD"
  env_set MQTT_HA_USER "$EXT_MQTT_USER"
  env_set MQTT_HA_PASSWORD "$EXT_MQTT_PASSWORD"
  ok "Using external broker credentials"
else
  for who in SERVER HA GATEWAY; do
    [[ -n "$(env_get "MQTT_${who}_PASSWORD")" ]] || env_set "MQTT_${who}_PASSWORD" "$(gen_pw)"
  done
  env_set MQTT_SERVER_USER gatemonitor
  env_set MQTT_HA_USER homeassistant
  env_set MQTT_GATEWAY_USER gateway
  ok "Broker passwords in $ENV_FILE (kept if they already existed)"
fi

env_set TZ "$TZ_NAME"
env_set HA_VERSION "$HA_VERSION"
env_set MQTT_HOST "$MQTT_HOST"
env_set MQTT_PORT "$MQTT_PORT"
env_set SIMULATE_DEVICES "$SIMULATE"
env_set GATE_MONITOR_PORT "$GATE_MONITOR_PORT"
env_set GATE_MONITOR_SRC ./server-src
[[ -n "$LATITUDE" ]] && env_set LATITUDE "$LATITUDE" && env_set LONGITUDE "$LONGITUDE"
HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
env_set PUBLIC_URL "http://${HOST_IP:-localhost}:$GATE_MONITOR_PORT"

if [[ -z "$EXTERNAL_BROKER" ]]; then
  # Build the password file inside the mosquitto image (hashes + correct owner),
  # so the host needs neither mosquitto tools nor root for chown.
  docker run --rm -v "$INSTALL_DIR/mosquitto:/m" \
    -e U1="$(env_get MQTT_SERVER_USER)" -e P1="$(env_get MQTT_SERVER_PASSWORD)" \
    -e U2="$(env_get MQTT_HA_USER)" -e P2="$(env_get MQTT_HA_PASSWORD)" \
    -e U3="$(env_get MQTT_GATEWAY_USER)" -e P3="$(env_get MQTT_GATEWAY_PASSWORD)" \
    eclipse-mosquitto:2.0.20 sh -c '
      umask 077 && : > /m/passwd &&
      mosquitto_passwd -b /m/passwd "$U1" "$P1" &&
      mosquitto_passwd -b /m/passwd "$U2" "$P2" &&
      mosquitto_passwd -b /m/passwd "$U3" "$P3" &&
      chown 1883:1883 /m/passwd && chmod 0600 /m/passwd' >/dev/null
  ok "Mosquitto users: gatemonitor, homeassistant, gateway"
fi

# ------------------------------------------------------------------- start
step "Starting containers (first build takes a few minutes on a Pi)"
cd "$INSTALL_DIR"
profiles=()
[[ -z "$EXTERNAL_BROKER" ]] && profiles=(--profile broker)
docker compose "${profiles[@]}" up -d --build --remove-orphans
ok "$(docker compose "${profiles[@]}" ps --format '{{.Name}} ({{.Status}})' | paste -sd, -)"

step "Waiting for services"
wait_http() {
  local url="$1" name="$2" tries="${3:-90}"
  for ((i = 0; i < tries; i++)); do
    if curl -fsS -o /dev/null "$url" 2>/dev/null; then ok "$name is up"; return 0; fi
    sleep 2
  done
  warn "$name did not answer at $url yet (check: docker compose logs)"; return 1
}
wait_http "http://127.0.0.1:$GATE_MONITOR_PORT/api/health" "Gate Monitor" || true
wait_http "http://127.0.0.1:8123/api/onboarding" "Home Assistant" 150 || true

# ------------------------------------------------------------- HA bootstrap
if [[ -n "$HA_USER" ]]; then
  step "Configuring Home Assistant"
  if [[ -z "$HA_PASSWORD" && -t 0 ]]; then
    read -r -s -p "    Password for HA user '$HA_USER': " HA_PASSWORD; echo
  fi
  [[ -n "$HA_PASSWORD" ]] || die "--ha-password required when not interactive"
  BROKER_FOR_HA="$MQTT_HOST"
  python3 "$SCRIPT_DIR/ha_bootstrap.py" --url http://127.0.0.1:8123 \
    --username "$HA_USER" --password "$HA_PASSWORD" \
    --mqtt-host "$BROKER_FOR_HA" --mqtt-port "$MQTT_PORT" \
    --mqtt-user "$(env_get MQTT_HA_USER)" --mqtt-password "$(env_get MQTT_HA_PASSWORD)" \
    || warn "HA auto-setup failed; finish onboarding in the browser and add MQTT manually"
fi

# ------------------------------------------------------------------ summary
IP="${HOST_IP:-<server-ip>}"
echo
echo -e "${GREEN}${BOLD}Done.${NC}"
cat <<EOF

  Gate Monitor     http://$IP:$GATE_MONITOR_PORT
  Home Assistant   http://$IP:8123   (Farm dashboard in the sidebar)
  Config & secrets $INSTALL_DIR  (.env holds broker passwords; chmod 600)

EOF
if [[ -z "$EXTERNAL_BROKER" ]]; then
  cat <<EOF
  House gateway (firmware/house_gateway/credentials.h):
      #define MQTT_SERVER   "$IP"
      #define MQTT_USER     "$(env_get MQTT_GATEWAY_USER)"
      #define MQTT_PASSWORD "$(env_get MQTT_GATEWAY_PASSWORD)"

EOF
fi
if [[ -z "$HA_USER" ]]; then
  cat <<EOF
  Home Assistant setup (one time):
    1. Open http://$IP:8123 and create your account.
    2. Settings -> Devices & services -> Add integration -> MQTT
         broker $MQTT_HOST  port $MQTT_PORT
         user $(env_get MQTT_HA_USER)  password: see MQTT_HA_PASSWORD in $ENV_FILE
       (or re-run this script with --ha-user/--ha-password to do it for you)

EOF
fi
cat <<EOF
  Phone:
    • Install the "Home Assistant" Companion app, connect to http://$IP:8123.
    • Set the "Farm notify service" helper to notify.mobile_app_<phone> for
      alerts with Close-gate buttons (see deploy/README.md).
    • Away from home: use Home Assistant Cloud (Nabu Casa) or a VPN such as
      Tailscale — don't port-forward 8123/$GATE_MONITOR_PORT/1883.

  Manage (from $INSTALL_DIR):
    docker compose ps                     status
    docker compose logs -f gate-monitor   follow logs
    re-run this script                    update to the current repo version
EOF
