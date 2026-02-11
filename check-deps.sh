#!/usr/bin/env bash
# Check that required system (non-Python) libraries are installed.
# Usage: ./check-deps.sh [--audio]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
RESET='\033[0m'

ok=0
warn=0
fail=0

check_lib() {
    local name="$1" reason="$2"
    if ldconfig -p 2>/dev/null | grep -q "$name"; then
        printf "${GREEN}OK${RESET}   %-28s  %s\n" "$name" "$reason"
        ok=$((ok + 1))
    else
        printf "${RED}MISS${RESET} %-28s  %s\n" "$name" "$reason"
        fail=$((fail + 1))
    fi
}

check_pkg() {
    local pkg="$1" reason="$2"
    if dpkg -s "$pkg" &>/dev/null; then
        printf "${GREEN}OK${RESET}   %-28s  %s\n" "$pkg" "$reason"
        ok=$((ok + 1))
    else
        printf "${RED}MISS${RESET} %-28s  %s\n" "$pkg" "$reason"
        fail=$((fail + 1))
    fi
}

check_optional_lib() {
    local name="$1" reason="$2"
    if ldconfig -p 2>/dev/null | grep -q "$name"; then
        printf "${GREEN}OK${RESET}   %-28s  %s\n" "$name" "$reason"
        ok=$((ok + 1))
    else
        printf "${YELLOW}SKIP${RESET} %-28s  %s\n" "$name" "$reason"
        warn=$((warn + 1))
    fi
}

check_audio=false
for arg in "$@"; do
    case "$arg" in
        --audio) check_audio=true ;;
        --help|-h)
            echo "Usage: $0 [--audio]"
            echo "  --audio   also check audio-related libraries (libportaudio)"
            exit 0
            ;;
        *) echo "unknown option: $arg"; exit 1 ;;
    esac
done

echo "=== pypicammotion system dependency check ==="
echo

echo "--- Core (picamera2 + OpenCV + H.264 encoding) ---"
check_lib  libcamera.so        "camera interface (picamera2)"
check_pkg  libcap-dev           "build dep for python-prctl (picamera2)"
check_lib  libopencv_core.so    "OpenCV core (motion detection)"
check_lib  libavcodec.so        "FFmpeg codecs (H.264 encoding)"
check_lib  libavformat.so       "FFmpeg container muxing"
check_lib  libswscale.so        "FFmpeg pixel format conversion"
echo

if $check_audio; then
    echo "--- Audio (sounddevice + PyAV muxing) ---"
    check_lib  libportaudio.so  "PortAudio (sounddevice audio capture)"
    echo
fi

echo "--- Optional (testing/development) ---"
check_optional_lib libmosquitto.so "MQTT broker client lib (paho-mqtt)"
echo

echo "---"
printf "Results: ${GREEN}%d ok${RESET}" "$ok"
[ "$warn" -gt 0 ] && printf ", ${YELLOW}%d skipped${RESET}" "$warn"
[ "$fail" -gt 0 ] && printf ", ${RED}%d missing${RESET}" "$fail"
echo

if [ "$fail" -gt 0 ]; then
    echo
    echo "Install missing libraries with:"
    echo "  sudo apt install <package-name>"
    exit 1
fi
