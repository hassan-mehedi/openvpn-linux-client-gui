#!/usr/bin/env bash
set -euo pipefail

REPO_URL="https://github.com/hassan-mehedi/openvpn-linux-client-gui.git"
CLONE_DIR="/tmp/openvpn3-client-linux-install"
BOLD='\033[1m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RED='\033[0;31m'
NC='\033[0m'

info()  { echo -e "${BOLD}${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${BOLD}${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${BOLD}${RED}[ERROR]${NC} $*"; }

# ── Detect distro ─────────────────────────────────────────────────────
detect_distro() {
    if [ ! -f /etc/os-release ]; then
        error "Cannot detect distribution — /etc/os-release not found."
        exit 1
    fi
    . /etc/os-release
    case "$ID" in
        fedora)         DISTRO_FAMILY="fedora" ;;
        rhel|centos|rocky|alma)  DISTRO_FAMILY="fedora" ;;
        ubuntu|debian|linuxmint|pop) DISTRO_FAMILY="debian" ;;
        *)
            error "Unsupported distribution: $ID"
            echo "Supported: Fedora, RHEL, Ubuntu, Debian, Linux Mint, Pop!_OS"
            exit 1
            ;;
    esac
    info "Detected distribution: $PRETTY_NAME ($DISTRO_FAMILY family)"
}

# ── Check prerequisites ──────────────────────────────────────────────
check_command() {
    if ! command -v "$1" &>/dev/null; then
        error "'$1' is required but not installed."
        exit 1
    fi
}

# ── Install OpenVPN 3 Linux ──────────────────────────────────────────
install_openvpn3_fedora() {
    if rpm -q openvpn3-client &>/dev/null || rpm -q openvpn3 &>/dev/null; then
        info "OpenVPN 3 Linux is already installed — skipping."
        return
    fi
    warn "OpenVPN 3 Linux is not installed. Installing..."
    sudo dnf install -y openvpn3-client
}

install_openvpn3_debian() {
    if dpkg -l openvpn3 2>/dev/null | grep -q '^ii'; then
        info "OpenVPN 3 Linux is already installed — skipping."
        return
    fi
    warn "OpenVPN 3 Linux is not installed. Installing..."
    # OpenVPN 3 Linux requires the official OpenVPN repository on Debian/Ubuntu
    if ! apt-cache show openvpn3 &>/dev/null; then
        info "Adding OpenVPN 3 repository..."
        sudo mkdir -p /etc/apt/keyrings
        curl -fsSL https://packages.openvpn.net/packages-repo.gpg | sudo tee /etc/apt/keyrings/openvpn.asc >/dev/null
        . /etc/os-release
        echo "deb [signed-by=/etc/apt/keyrings/openvpn.asc] https://packages.openvpn.net/openvpn3/debian $VERSION_CODENAME main" \
            | sudo tee /etc/apt/sources.list.d/openvpn3.list >/dev/null
        sudo apt-get update
    fi
    sudo apt-get install -y openvpn3
}

# ── Install build dependencies ────────────────────────────────────────
install_build_deps_fedora() {
    info "Installing build dependencies..."
    sudo dnf install -y \
        git \
        python3-build \
        python3-devel \
        python3-setuptools \
        python3-wheel \
        rpm-build \
        pyproject-rpm-macros \
        gtk4 \
        libadwaita \
        libsecret \
        python3-gobject \
        python3-dbus
}

install_build_deps_debian() {
    info "Installing build dependencies..."
    sudo apt-get install -y \
        git \
        python3-build \
        python3-installer \
        python3-setuptools \
        python3-wheel \
        debhelper \
        dh-python \
        python3-all \
        gir1.2-gtk-4.0 \
        gir1.2-adw-1 \
        gir1.2-secret-1 \
        python3-gi \
        python3-dbus
}

# ── Clone and build ──────────────────────────────────────────────────
clone_repo() {
    if [ -d "$CLONE_DIR" ]; then
        info "Removing previous install directory..."
        rm -rf "$CLONE_DIR"
    fi
    info "Cloning repository..."
    git clone --depth 1 "$REPO_URL" "$CLONE_DIR"
}

build_and_install_fedora() {
    info "Building RPM package..."
    cd "$CLONE_DIR"
    make rpm-build
    info "Installing RPM package..."
    make rpm-install
}

build_and_install_debian() {
    info "Building DEB package..."
    cd "$CLONE_DIR"
    make deb-build
    info "Installing DEB package..."
    make deb-install
}

# ── Cleanup ───────────────────────────────────────────────────────────
cleanup() {
    info "Cleaning up build directory..."
    rm -rf "$CLONE_DIR"
}

# ── Main ──────────────────────────────────────────────────────────────
main() {
    echo ""
    echo -e "${BOLD}OpenVPN 3 Linux Client GUI — Installer${NC}"
    echo "────────────────────────────────────────"
    echo ""

    detect_distro
    check_command git
    check_command curl

    if [ "$DISTRO_FAMILY" = "fedora" ]; then
        install_openvpn3_fedora
        install_build_deps_fedora
    else
        install_openvpn3_debian
        install_build_deps_debian
    fi

    clone_repo

    if [ "$DISTRO_FAMILY" = "fedora" ]; then
        build_and_install_fedora
    else
        build_and_install_debian
    fi

    cleanup

    echo ""
    info "Installation complete!"
    echo ""
    echo "  Launch the GUI:  ovpn3-linux-gui"
    echo "  Use the CLI:     ovpn-gui --help"
    echo "  Run diagnostics: ovpn-gui doctor"
    echo ""
}

main "$@"
