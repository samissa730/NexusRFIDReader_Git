export interface DeviceValidationRequest {
    deviceId: string;
    operation: "enroll" | "renew";
    bootstrapToken?: string;
}

export interface DeviceValidationResult {
    isAllowed: boolean;
    reason?: string;
}

export async function validateDevice(request: DeviceValidationRequest): Promise<DeviceValidationResult> {
    // Local stub.
    // Replace in higher environments with internal .NET API call.

    if (request.operation === "enroll") {
        if (!request.bootstrapToken) {
            return { isAllowed: false, reason: "Missing bootstrap token" };
        }
        return { isAllowed: true };
    }

    if (request.operation === "renew") {
        return { isAllowed: true };
    }

    return { isAllowed: false, reason: "Unknown operation" };
}