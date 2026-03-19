import { Request } from "express";

export interface ClientCertificateIdentity {
    subject: string;
    commonName?: string;
    isPresent: boolean;
}

export function getClientCertificateIdentity(req: Request): ClientCertificateIdentity {
    const socket: any = req.socket;

    if (!socket || typeof socket.getPeerCertificate !== "function") {
        return { subject: "", isPresent: false };
    }

    const cert = socket.getPeerCertificate();

    if (!cert || Object.keys(cert).length === 0) {
        return { subject: "", isPresent: false };
    }

    const subject = cert.subject ? JSON.stringify(cert.subject) : "";
    const commonName = cert.subject?.CN;

    return {
        subject,
        commonName,
        isPresent: true
    };
}