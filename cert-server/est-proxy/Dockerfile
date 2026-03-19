FROM node:20-slim

# 1. Install necessary tools for downloading and running step-cli
RUN apt-get update && apt-get install -y \
    openssl \
    curl \
    ca-certificates \
    tar \
 && rm -rf /var/lib/apt/lists/*

# 2. Download and install step-cli (Architecture-aware for both Apple Silicon and Azure)
RUN ARCH=$(dpkg --print-architecture) && \
    if [ "$ARCH" = "arm64" ]; then STEP_ARCH="arm64"; else STEP_ARCH="amd64"; fi && \
    curl -L "https://github.com/smallstep/cli/releases/latest/download/step_linux_${STEP_ARCH}.tar.gz" -o step.tar.gz && \
    tar -xzf step.tar.gz && \
    install -m 0755 $(find . -name step -type f) /usr/local/bin/step && \
    rm -rf step.tar.gz step_* && \
    step version

WORKDIR /app

RUN mkdir -p /app/tls /home/step/secrets /home/step/certs

# 2. Copy the certs used by the proxy to listen on HTTPS
# Map these to the paths your server.ts expects
COPY ./certs/server.crt /app/tls/server.crt
COPY ./certs/server.key /app/tls/server.key
COPY ./certs/root_ca.crt /app/tls/client-ca-chain.pem

# 3. Copy Step-CA integration files (as you had before)
COPY ./certs/ /home/step/certs/
COPY ./certs/password /home/step/secrets/

# 4. Build the App
COPY package*.json tsconfig.json ./
RUN npm install
COPY src ./src
RUN npm run build

EXPOSE 9443

# 5. Run Node.js directly
CMD ["node", "dist/server.js"]