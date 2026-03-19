import fs from "fs";

export function readCaChain(rootPath: string, intermediatePath: string): Buffer {
    const root = fs.readFileSync(rootPath);
    const intermediate = fs.readFileSync(intermediatePath);
    return Buffer.concat([root, Buffer.from("\n"), intermediate]);
}