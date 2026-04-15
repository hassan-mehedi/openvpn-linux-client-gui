#!/usr/bin/env bash
set -euo pipefail

GITHUB_REPO="hassan-mehedi/openvpn-linux-client-gui"
GITHUB_API_URL="https://api.github.com/repos/${GITHUB_REPO}"
TMP_DIR=""
RELEASE_JSON=""
PACKAGE_KIND=""
PACKAGE_NAME=""
PACKAGE_URL=""
PACKAGE_PATH=""
DISTRO_FAMILY=""
DISTRO_ID=""
DISTRO_VERSION_ID=""
DISTRO_CODENAME=""
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BOLD}${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${BOLD}${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${BOLD}${RED}[ERROR]${NC} $*"; }

as_root() {
    if [ "$(id -u)" -eq 0 ]; then
        "$@"
    else
        sudo "$@"
    fi
}

version_ge() {
    [ "$(printf '%s\n%s\n' "$2" "$1" | sort -V | head -n1)" = "$2" ]
}

cleanup() {
    if [ -n "${TMP_DIR:-}" ] && [ -d "$TMP_DIR" ]; then
        rm -rf "$TMP_DIR"
    fi
}

trap cleanup EXIT

detect_distro() {
    if [ ! -f /etc/os-release ]; then
        error "Cannot detect distribution — /etc/os-release not found."
        exit 1
    fi
    . /etc/os-release
    DISTRO_ID="$ID"
    DISTRO_VERSION_ID="${VERSION_ID:-}"
    DISTRO_CODENAME="${VERSION_CODENAME:-${UBUNTU_CODENAME:-}}"

    case "$ID" in
        fedora)
            DISTRO_FAMILY="fedora"
            PACKAGE_KIND="rpm"
            ;;
        ubuntu|debian|linuxmint|pop)
            DISTRO_FAMILY="debian"
            PACKAGE_KIND="deb"
            ;;
        *)
            error "Unsupported distribution: $ID"
            echo "Supported: Fedora, Ubuntu, Debian, Linux Mint, Pop!_OS"
            exit 1
            ;;
    esac

    case "$DISTRO_ID" in
        fedora)
            if ! version_ge "$DISTRO_VERSION_ID" "40"; then
                error "Fedora ${DISTRO_VERSION_ID} is not supported by this installer."
                echo "Supported Fedora releases: 40 or newer."
                exit 1
            fi
            ;;
        ubuntu|pop)
            if ! version_ge "$DISTRO_VERSION_ID" "22.04"; then
                error "${PRETTY_NAME} is not supported by this installer."
                echo "Supported Ubuntu-based releases: 22.04 or newer."
                exit 1
            fi
            ;;
        debian)
            if ! version_ge "$DISTRO_VERSION_ID" "12"; then
                error "Debian ${DISTRO_VERSION_ID} is not supported by this installer."
                echo "Supported Debian releases: 12 or newer."
                exit 1
            fi
            ;;
        linuxmint)
            if ! version_ge "$DISTRO_VERSION_ID" "21"; then
                error "Linux Mint ${DISTRO_VERSION_ID} is not supported by this installer."
                echo "Supported Linux Mint releases: 21 or newer."
                exit 1
            fi
            ;;
    esac

    info "Detected distribution: $PRETTY_NAME"
}

debian_repo_codename() {
    case "$DISTRO_ID" in
        linuxmint|pop)
            printf '%s\n' "${UBUNTU_CODENAME:-}"
            ;;
        *)
            printf '%s\n' "$DISTRO_CODENAME"
            ;;
    esac
}

check_command() {
    if ! command -v "$1" &>/dev/null; then
        error "'$1' is required but not installed."
        exit 1
    fi
}

ensure_openvpn3_repo_debian() {
    local repo_codename
    repo_codename="$(debian_repo_codename)"
    if [ -z "$repo_codename" ]; then
        error "Unable to determine the repository codename for ${DISTRO_ID}."
        exit 1
    fi

    if ! apt-cache show openvpn3 &>/dev/null; then
        info "Adding OpenVPN 3 repository for ${repo_codename}..."
        as_root mkdir -p /etc/apt/keyrings
        curl -fsSL https://packages.openvpn.net/packages-repo.gpg \
            | as_root tee /etc/apt/keyrings/openvpn.asc >/dev/null
        printf 'deb [signed-by=/etc/apt/keyrings/openvpn.asc] https://packages.openvpn.net/openvpn3/debian %s main\n' "$repo_codename" \
            | as_root tee /etc/apt/sources.list.d/openvpn3.list >/dev/null
        as_root apt-get update
    fi
}

fetch_latest_release_metadata() {
    info "Resolving the latest stable release..."
    RELEASE_JSON="$(
        curl -fsSL \
            -H "Accept: application/vnd.github+json" \
            -H "User-Agent: openvpn3-client-linux-installer" \
            "${GITHUB_API_URL}/releases/latest"
    )"

    if [ -z "$RELEASE_JSON" ]; then
        error "Failed to read release metadata from GitHub."
        exit 1
    fi
}

select_release_asset() {
    local kind="$1"

    mapfile -t asset_lines < <(
        printf '%s' "$RELEASE_JSON" | python3 - "$kind" <<'PY'
import json
import sys

kind = sys.argv[1]
release = json.load(sys.stdin)
assets = release.get("assets") or []

def matches(name: str) -> bool:
    if kind == "deb":
        return name.endswith(".deb")
    if kind == "rpm":
        return name.endswith(".noarch.rpm")
    return False

for asset in assets:
    name = asset.get("name", "")
    if matches(name):
        print(name)
        print(asset.get("browser_download_url", ""))
        print(release.get("tag_name", ""))
        break
else:
    raise SystemExit(1)
PY
    ) || {
        error "No ${kind} package asset was found in the latest stable release."
        exit 1
    }

    PACKAGE_NAME="${asset_lines[0]:-}"
    PACKAGE_URL="${asset_lines[1]:-}"

    if [ -z "$PACKAGE_NAME" ] || [ -z "$PACKAGE_URL" ]; then
        error "Release metadata did not include a usable ${kind} asset."
        exit 1
    fi

    info "Selected release asset: ${PACKAGE_NAME}"
}

download_release_asset() {
    TMP_DIR="$(mktemp -d /tmp/openvpn3-client-linux-install.XXXXXX)"
    PACKAGE_PATH="${TMP_DIR}/${PACKAGE_NAME}"
    info "Downloading ${PACKAGE_NAME}..."
    curl -fL --retry 3 --retry-delay 2 -o "$PACKAGE_PATH" "$PACKAGE_URL"
}

install_release_debian() {
    ensure_openvpn3_repo_debian
    info "Installing ${PACKAGE_NAME} with apt..."
    as_root apt-get update
    as_root env DEBIAN_FRONTEND=noninteractive apt-get install -y "$PACKAGE_PATH"
}

install_release_fedora() {
    info "Installing ${PACKAGE_NAME} with dnf..."
    as_root dnf install -y "$PACKAGE_PATH"
}

main() {
    echo ""
    echo -e "${BOLD}OpenVPN 3 Linux Client GUI — Installer${NC}"
    echo "────────────────────────────────────────"
    echo ""

    detect_distro
    check_command curl
    check_command python3
    if [ "$(id -u)" -ne 0 ]; then
        check_command sudo
    fi
    if [ "$DISTRO_FAMILY" = "debian" ]; then
        check_command apt-get
        check_command apt-cache
    else
        check_command dnf
    fi

    fetch_latest_release_metadata
    select_release_asset "$PACKAGE_KIND"
    download_release_asset

    if [ "$PACKAGE_KIND" = "rpm" ]; then
        install_release_fedora
    else
        install_release_debian
    fi

    echo ""
    info "Installation complete!"
    echo ""
    echo "  Launch the GUI:  ovpn3-linux-gui"
    echo "  Use the CLI:     ovpn-gui --help"
    echo "  Run diagnostics: ovpn-gui doctor"
    echo ""
}

main "$@"
