# EST proxy: exposes EST endpoints and uses step-ca (via step CLI) as backend.
# Uses step-ca image so step CLI is present and compatible.
FROM smallstep/step-ca:latest

USER root
RUN apk add --no-cache python3 py3-pip openssl wget \
    && pip3 install --break-system-packages flask cryptography gunicorn

WORKDIR /app
COPY app.py .

# Self-signed cert for EST (HTTPS); clients use verify_ssl=False for local testing
RUN openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=est-proxy"

ENV EST_BOOTSTRAP_TOKEN=changeme
ENV STEP_CA_URL=https://step-ca:8443
EXPOSE 9443

CMD ["python3", "-m", "gunicorn", "-b", "0.0.0.0:9443", "-w", "1", "--certfile", "/app/cert.pem", "--keyfile", "/app/key.pem", "app:app"]
