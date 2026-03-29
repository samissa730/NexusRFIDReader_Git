FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DISPLAY=:0 \
    XDG_RUNTIME_DIR=/tmp/runtime-root

RUN apt-get update && apt-get install -y --no-install-recommends \
    bash \
    sudo \
    iproute2 \
    isc-dhcp-client \
    x11-xserver-utils \
    libx11-6 \
    libx11-xcb1 \
    libxcb1 \
    libxcb-cursor0 \
    libxcb-render0 \
    libxcb-shape0 \
    libxcb-xfixes0 \
    libxfixes3 \
    libxi6 \
    libxrender1 \
    libxcb-xinerama0 \
    libgl1 \
    libegl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/nexusrfid

COPY requirements.txt /opt/nexusrfid/requirements.txt
RUN pip install --no-cache-dir -r /opt/nexusrfid/requirements.txt && \
    pip install --no-cache-dir azure-iot-device azure-storage-blob

COPY . /opt/nexusrfid

RUN chmod +x /opt/nexusrfid/docker/prod/entrypoint.sh

ENTRYPOINT ["/opt/nexusrfid/docker/prod/entrypoint.sh"]
