import fs from "fs";
import { execSync } from "child_process";

export function extractCommonNameFromCsr(csrPath: string): string {
    // OpenSSL 3.x output format for -subject is often:
    // subject=CN = PI-DEVICE-001, O = NexusLocate
    // OR
    // subject= /CN=PI-DEVICE-001/O=NexusLocate
    const output = execSync(`openssl req -in ${csrPath} -noout -subject`).toString();
    
    // Try to match CN= followed by value until comma or slash or end of line
    const match = output.match(/CN\s*=\s*([^,\/\n\r]+)/);

    if (!match) {
        throw new Error(`CSR missing CN. Output was: ${output}`);
    }

    return match[1].trim();
}

export function writeCsrToFile(filePath: string, data: Buffer): void {
    fs.writeFileSync(filePath, data);
}