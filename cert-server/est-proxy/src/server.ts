import http from "http";
import https from "https";
import fs from "fs";
import app from "./app";
import { config } from "./config";

const TLS_CERT = "/app/tls/server.crt";
const TLS_KEY = "/app/tls/server.key";
const TLS_CA = "/app/tls/client-ca-chain.pem";

function hasTlsFiles(): boolean {
    try {
        return fs.existsSync(TLS_CERT) && fs.existsSync(TLS_KEY) && fs.existsSync(TLS_CA);
    } catch {
        return false;
    }
}

if (hasTlsFiles()) {
    const server = https.createServer(
        {
            cert: fs.readFileSync(TLS_CERT),
            key: fs.readFileSync(TLS_KEY),
            ca: fs.readFileSync(TLS_CA),
            requestCert: true,
            rejectUnauthorized: false
        },
        app
    );
    server.listen(9443, () => {
        console.log("EST Proxy listening on 9443 (HTTPS)");
    });
} else {
    const server = http.createServer(app);
    server.listen(config.port, () => {
        console.log(`EST Proxy listening on ${config.port} (HTTP, TLS via socat on 9443)`);
    });
}