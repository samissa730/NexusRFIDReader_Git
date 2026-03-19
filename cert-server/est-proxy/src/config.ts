export const config = {
    bootstrapToken: process.env.EST_BOOTSTRAP_TOKEN || "changeme",
    stepCaUrl: process.env.STEP_CA_URL || "https://step-ca:8443",
    stepPasswordFile: process.env.STEP_CA_PASSWORD_FILE || "/home/step/secrets/password",
    stepRootCert: process.env.STEP_CA_ROOT_CERT || "/home/step/certs/root_ca.crt",
    stepProvisioner: process.env.STEP_CA_PROVISIONER || "admin",
    rootCertPath: "/home/step/certs/root_ca.crt",
    intermediateCertPath: "/home/step/certs/intermediate.crt",
    port: 8080
};