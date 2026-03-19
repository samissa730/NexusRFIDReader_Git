# EST Proxy for step-ca

This service exposes **EST (RFC 7030)** endpoints and uses **step-ca** as the backend CA. step-ca does not implement EST natively; this proxy forwards:

- **POST /est/simpleenroll** — accepts a CSR and bootstrap token, gets a one-time token from step-ca, signs the CSR via step-ca, returns the issued certificate (DER).
- **GET /est/cacerts** — returns the step-ca intermediate certificate (DER).

## Build and run

From `utils_Test`:

```bash
docker compose up -d --build
```

EST is available at **https://localhost:9443/est**. Use bootstrap token `changeme` (or set `EST_BOOTSTRAP_TOKEN` in docker-compose).

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `EST_BOOTSTRAP_TOKEN` | `changeme` | Token required in `Authorization: Bearer <token>` for /est requests |
| `STEP_CA_URL` | `https://step-ca:8443` | step-ca base URL (must be reachable from the proxy container) |
| `STEP_CA_PASSWORD_FILE` | `/home/step/secrets/password` | Path to CA password file (for `step ca token`) |
| `STEP_CA_ROOT_CERT` | `/home/step/certs/root_ca.crt` | Path to root CA cert (for verifying step-ca TLS) |
| `STEP_CA_PROVISIONER` | `admin` | step-ca provisioner name for token generation |

## Testing

After `docker compose up -d --build`:

```bash
python test_est_enrollment.py
# or
python test_bootstrap_enrollment.py
```

Use **EST Server URL** `https://localhost:9443/est` and **Bootstrap Token** `changeme` (or whatever you set in docker-compose).
