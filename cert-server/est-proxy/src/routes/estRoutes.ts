import { Router, Request, Response } from "express";
import fs from "fs";
import os from "os";
import path from "path";
import { config } from "../config";
import { requireBearerToken, validateBootstrapToken } from "../services/authService";
import { validateDevice } from "../services/validationService";
import { extractCommonNameFromCsr, writeCsrToFile } from "../services/csrService";
import { generateOneTimeToken, signCsr, readIssuedCertificate } from "../services/stepCaService";
import { readCaChain } from "../utils/fileUtils";
import { getClientCertificateIdentity } from "../services/clientCertService";

const router = Router();

router.get("/health", (_req: Request, res: Response) => {
    res.json({ status: "ok" });
});

router.get("/est/cacerts", (_req: Request, res: Response) => {
    try {
        const chain = readCaChain(config.rootCertPath, config.intermediateCertPath);
        res.type("application/x-pem-file").send(chain);
    } catch (err: any) {
        res.status(500).send(err.toString());
    }
});

router.post("/est/simpleenroll", async (req: Request, res: Response) => {
    const token = requireBearerToken(req, res);
    if (!token) return;

    if (!validateBootstrapToken(token)) {
        return res.status(403).send("Forbidden");
    }

    if (!req.body || req.body.length === 0) {
        return res.status(400).send("Missing CSR");
    }

    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "csr-"));
    const csrPath = path.join(tempDir, "request.pem");
    const certPath = path.join(tempDir, "device.crt");

    try {
        writeCsrToFile(csrPath, req.body as Buffer);

        const deviceId = extractCommonNameFromCsr(csrPath);

        const validation = await validateDevice({
            deviceId,
            operation: "enroll",
            bootstrapToken: token
        });

        if (!validation.isAllowed) {
            return res.status(403).send(validation.reason || "Enrollment denied");
        }

        const oneTimeToken = generateOneTimeToken(deviceId);
        signCsr(csrPath, certPath, oneTimeToken);

        const cert = readIssuedCertificate(certPath);
        res.type("application/x-pem-file").send(cert);
    } catch (err: any) {
        res.status(500).send(err.toString());
    } finally {
        try {
            fs.rmSync(tempDir, { recursive: true, force: true });
        } catch {
            // ignore cleanup errors
        }
    }
});

router.post("/est/simplereenroll", async (req: Request, res: Response) => {
    if (!req.body || req.body.length === 0) {
        return res.status(400).send("Missing CSR");
    }

    const clientIdentity = getClientCertificateIdentity(req);

    if (!clientIdentity.isPresent || !clientIdentity.commonName) {
        return res.status(401).send("Client certificate required");
    }

    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "csr-renew-"));
    const csrPath = path.join(tempDir, "request.pem");
    const certPath = path.join(tempDir, "device-renewed.crt");

    try {
        writeCsrToFile(csrPath, req.body as Buffer);

        const csrDeviceId = extractCommonNameFromCsr(csrPath);
        const authenticatedDeviceId = clientIdentity.commonName;

        if (csrDeviceId !== authenticatedDeviceId) {
            return res.status(403).send("CSR identity does not match client certificate");
        }

        const validation = await validateDevice({
            deviceId: authenticatedDeviceId,
            operation: "renew"
        });

        if (!validation.isAllowed) {
            return res.status(403).send(validation.reason || "Renewal denied");
        }

        const oneTimeToken = generateOneTimeToken(authenticatedDeviceId);
        signCsr(csrPath, certPath, oneTimeToken);

        const cert = readIssuedCertificate(certPath);
        res.type("application/x-pem-file").send(cert);
    } catch (err: any) {
        res.status(500).send(err.toString());
    } finally {
        try {
            fs.rmSync(tempDir, { recursive: true, force: true });
        } catch {
            // ignore cleanup errors
        }
    }
});

export default router;