import { Request, Response } from "express";
import { config } from "../config";

export function requireBearerToken(req: Request, res: Response): string | null {
    const auth = req.header("Authorization");

    if (!auth || !auth.startsWith("Bearer ")) {
        res.status(401).send("Unauthorized");
        return null;
    }

    const token = auth.substring(7).trim();

    if (!token) {
        res.status(401).send("Unauthorized");
        return null;
    }

    return token;
}

export function validateBootstrapToken(token: string): boolean {
    // Local test behavior only.
    // In higher env this should call internal validation API.
    return token === config.bootstrapToken;
}