# Runner image for EST proxy (code from env) and step-ca init (jq for config patch).
# No app code copied; proxy script is provided via EST_PROXY_SCRIPT in compose.
# step-cli is required for "step ca init" in step-ca-init (smallstep/step-ca image has no CLI).
FROM smallstep/step-ca:latest

USER root
# Enable community repo for step-cli (needed for "step ca init" in step-ca-init)
RUN sed -i '/community/s/^#//' /etc/apk/repositories 2>/dev/null || true \
    && apk update \
    && apk add --no-cache python3 py3-pip openssl wget jq curl step-cli socat \
    && pip3 install --break-system-packages flask cryptography gunicorn

WORKDIR /app
# SAN so TLS works when clients connect to 127.0.0.1 or localhost (e.g. host-side EST test)
RUN openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes \
    -subj "/CN=est-proxy" \
    -addext "subjectAltName=DNS:est-proxy,DNS:localhost,IP:127.0.0.1" \
    && cat cert.pem key.pem > combined.pem && chmod 600 combined.pem \
    && chown -R step:step /app

ENV EST_BOOTSTRAP_TOKEN=changeme
ENV STEP_CA_URL=https://step-ca:8443
EXPOSE 9443

USER step
