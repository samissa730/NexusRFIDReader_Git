import { execSync } from "child_process";
import fs from "fs";
import { config } from "../config";

export function generateOneTimeToken(deviceId: string): string {
    return execSync(
        `step ca token "${deviceId}" --password-file "${config.stepPasswordFile}" --ca-url "${config.stepCaUrl}" --root "${config.stepRootCert}" --provisioner "${config.stepProvisioner}"`
    )
        .toString()
        .trim();
}

export function signCsr(csrPath: string, certPath: string, token: string): void {
    execSync(
        `step ca sign "${csrPath}" "${certPath}" --token "${token}" --ca-url "${config.stepCaUrl}" --root "${config.stepRootCert}"`
    );
}

export function readIssuedCertificate(certPath: string): Buffer {
    return fs.readFileSync(certPath);
}