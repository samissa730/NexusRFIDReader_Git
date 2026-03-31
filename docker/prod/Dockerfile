FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:0 \
    XDG_RUNTIME_DIR=/tmp/runtime-root

# Qt 6 xcb platform plugin needs a fuller xcb stack than a minimal kiosk .deb Depends list.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    sudo \
    iproute2 \
    isc-dhcp-client \
    x11-xserver-utils \
    libfontconfig1 \
    libfreetype6 \
    fonts-dejavu-core \
    libxkbcommon0 \
    libxkbcommon-x11-0 \
    libdbus-1-3 \
    libglib2.0-0 \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-xkb1 \
    libxcb-icccm4 \
    libxcb-image0 \
    libxcb-keysyms1 \
    libxcb-render0 \
    libxcb-render-util0 \
    libxcb-shape0 \
    libxcb-sync1 \
    libxcb-util1 \
    libxcb-xfixes0 \
    libxfixes3 \
    libxi6 \
    libxrender1 \
    libxcb-xinerama0 \
    libsm6 \
    libice6 \
    libgl1 \
    libegl1 \
    libdrm2 \
    libgbm1 \
    && rm -rf /var/lib/apt/lists/* \
    && ldconfig

WORKDIR /opt/nexusrfid

COPY requirements.txt /opt/nexusrfid/requirements.txt
RUN pip install --no-cache-dir -r /opt/nexusrfid/requirements.txt && \
    pip install --no-cache-dir azure-iot-device azure-storage-blob

# Fail build if PySide6's xcb plugin has unresolved shared-library deps (wheel layout varies: Qt/ vs Qt6/).
RUN python3 <<'PY'
import glob, os, subprocess, sys
import PySide6

base = PySide6.__path__[0]
cands = glob.glob(os.path.join(base, "**", "libqxcb.so"), recursive=True)
if not cands:
    print("libqxcb.so not found under", base, file=sys.stderr)
    sys.exit(1)
qxcb = cands[0]
print("Checking", qxcb)
out = subprocess.check_output(["ldd", qxcb], text=True)
print(out)
if "not found" in out:
    print("Missing deps for libqxcb.so", file=sys.stderr)
    sys.exit(1)
PY

COPY . /opt/nexusrfid

RUN chmod +x /opt/nexusrfid/docker/prod/entrypoint.sh

ENTRYPOINT ["/opt/nexusrfid/docker/prod/entrypoint.sh"]
