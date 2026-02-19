# Runner image for EST proxy (code from env) and step-ca init (jq for config patch).
# No app code copied; proxy script is provided via EST_PROXY_SCRIPT in compose.
FROM smallstep/step-ca:latest

USER root
RUN apk add --no-cache python3 py3-pip openssl wget jq curl \
    && pip3 install --break-system-packages flask cryptography gunicorn

WORKDIR /app
RUN openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=est-proxy"

ENV EST_BOOTSTRAP_TOKEN=changeme
ENV STEP_CA_URL=https://step-ca:8443
EXPOSE 9443

USER step
