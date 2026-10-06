#!/usr/bin/env bash
# Ubuntu/WSL bootstrap. No GNU Make or system Python required to start.
set -Eeuo pipefail
source_path="${BASH_SOURCE[0]}"
script_dir="${source_path%/*}"
[[ "$script_dir" != "$source_path" ]] || script_dir=.
root="$(cd -- "$script_dir/.." && pwd)"
mode=setup
install_global=0
for arg in "$@"; do
  case "$arg" in
    --install-global) install_global=1 ;;
    --check) mode=check ;;
    --plan) mode=plan ;;
    --env-only) mode=env ;;
    *) echo "Unknown option: $arg. Use --install-global, --check or --plan." >&2; exit 2 ;;
  esac
done
die() { echo "$*" >&2; exit 1; }
trap 'echo "Setup stopped at line $LINENO. Fix the error and rerun; existing .env and volumes are preserved." >&2' ERR
if [[ "$mode" == plan ]]; then
  echo 'PLAN ONLY: no files, installs, containers or migrations changed.'
  echo 'Global (opt-in, Ubuntu): apt git/curl/make/build-essential; nvm + Node 22; uv; Docker Engine + Compose on native Ubuntu only.'
  echo 'WSL: use Windows Docker Desktop integration, not a second Docker Engine.'
  echo 'User Python 3.12; local preserved/generated .env, frozen dependencies, healthy services, buckets, verify, migrate, Django check, frontend build.'
  exit 0
fi
if [[ "$mode" == env ]]; then
  exec node "$root/scripts/development/environment.cjs" env
fi
[[ "$(uname -s)" == Linux ]] || die 'Use the .ps1 script on Windows; automatic global installation supports Ubuntu only.'
[[ -f /etc/os-release ]] || die 'Missing Linux distribution information.'
source /etc/os-release
[[ "$ID" == ubuntu ]] || die 'This bootstrap supports Ubuntu 22.04/24.04/26.04 and Ubuntu under WSL only.'
case "$VERSION_ID" in 22.04|24.04|26.04) ;; *) die 'Unsupported Ubuntu version.' ;; esac
export PATH="$HOME/.local/bin:$PATH"
export NVM_DIR="${NVM_DIR:-$HOME/.nvm}"
if [[ -s "$NVM_DIR/nvm.sh" ]]; then source "$NVM_DIR/nvm.sh"; fi
is_wsl=0
if grep -qi microsoft /proc/sys/kernel/osrelease; then is_wsl=1; fi
if [[ "$mode" == setup && "$install_global" == 1 ]]; then
  [[ "$EUID" != 0 ]] || die 'Run as your normal developer user, not root (sudo is used only for system packages).'
  sudo apt-get update
  sudo apt-get install -y git curl ca-certificates make build-essential
  if ! command -v node >/dev/null || [[ "$(node -p 'process.platform')" != linux ]] || [[ "$(node -p 'Number(process.versions.node.split(".")[0]) < 22')" == true ]]; then
    if [[ ! -s "$NVM_DIR/nvm.sh" ]]; then
      curl --fail --location --retry 3 https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.8/install.sh | bash
    fi
    source "$NVM_DIR/nvm.sh"
    nvm install 22
    nvm alias default 22
  fi
  if ! command -v uv >/dev/null; then curl --fail --location --retry 3 https://astral.sh/uv/install.sh | sh; fi
  if ! command -v docker >/dev/null && [[ "$is_wsl" == 0 ]]; then
    # Refuse to replace an existing alternate runtime/package installation.
    for package in docker.io docker-compose docker-compose-v2 podman-docker containerd runc; do
      if dpkg-query -W -f='${Status}' "$package" 2>/dev/null | grep -q 'install ok installed'; then
        die "Existing $package conflicts with Docker CE. Review it manually; nothing will be uninstalled."
      fi
    done
    sudo install -m 0755 -d /etc/apt/keyrings
    sudo curl --fail --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    sudo chmod a+r /etc/apt/keyrings/docker.asc
    printf 'Types: deb\nURIs: https://download.docker.com/linux/ubuntu\nSuites: %s\nComponents: stable\nArchitectures: %s\nSigned-By: /etc/apt/keyrings/docker.asc\n' \
      "${UBUNTU_CODENAME:-$VERSION_CODENAME}" "$(dpkg --print-architecture)" | sudo tee /etc/apt/sources.list.d/docker.sources >/dev/null
    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    sudo systemctl start docker
  fi
fi
for tool in git node npm uv docker; do
  command -v "$tool" >/dev/null || die "Missing $tool. Use --install-global. On WSL enable Docker Desktop > Settings > Resources > WSL integration first."
done
[[ "$(node -p 'process.platform')" == linux ]] || die 'WSL must use Linux Node/npm, not Windows executables. Install using --install-global in WSL.'
[[ "$(node -p 'Number(process.versions.node.split(".")[0]) >= 22')" == true ]] || die 'Node >=22 required; rerun --install-global.'
docker compose version
docker info >/dev/null || die 'Docker unavailable or permission denied. Start Docker; on Ubuntu configure socket access (see docs/07-development/tooling.html); on WSL enable Desktop integration. Then rerun.'
[[ "$(docker info --format '{{.OSType}}')" == linux ]] || die 'Linux containers are required.'
case "$(docker context show)" in default|desktop-linux) ;; *) die 'Use a local Docker context, not a remote server.' ;; esac
case "$(docker context inspect --format '{{.Endpoints.docker.Host}}')" in unix://*) ;; *) die 'Use a local Unix Docker socket, not a remote endpoint.' ;; esac
node "$root/scripts/development/environment.cjs" preflight
if [[ "$mode" == check ]]; then
  [[ -f "$root/src/backend/.env" && -f "$root/src/frontend/.env.local" && -x "$root/src/backend/.venv/bin/python" && -x "$root/src/frontend/node_modules/.bin/next" ]] || die 'Local dependencies/env missing; run setup.'
  "$root/src/backend/.venv/bin/python" "$root/scripts/development/verify-services.py"
  (cd "$root/src/backend" && .venv/bin/python manage.py check && .venv/bin/python manage.py migrate --check)
  echo 'CHECK PASSED: local dependencies/services and migrations available. Setup includes a frontend build check.'
  exit 0
fi
uv python install 3.12
node "$root/scripts/development/environment.cjs" env
node "$root/scripts/development/environment.cjs" preflight
(cd "$root/src/backend" && uv sync --frozen --python 3.12)
(cd "$root/src/frontend" && npm ci --no-audit --no-fund)
compose=(docker compose -f "$root/infrastructure/docker-compose.dev.yml")
"${compose[@]}" up -d --wait --wait-timeout 180 postgres redis seaweedfs
"${compose[@]}" run --rm seaweedfs-init
(cd "$root/src/backend" && uv run --frozen python "$root/scripts/development/verify-services.py" && uv run --frozen python manage.py migrate --noinput && uv run --frozen python manage.py check)
(cd "$root/src/frontend" && npm run build)
echo 'SETUP PASSED. In separate terminals: make dev-backend; make dev-worker; make dev-frontend.'
echo 'CVAT access and model artifacts still need project configuration. Setup does not install CVAT or create administrator accounts.'
