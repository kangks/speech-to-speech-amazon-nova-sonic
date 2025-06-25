/**
 * Converts a base64 encoded string to a Float32Array
 * Used for converting audio data received from the server
 * @param {string} base64String - Base64 encoded audio data
 * @returns {Float32Array} - Audio data as Float32Array
 */
export function base64ToFloat32Array(base64String) {
    const binaryString = atob(base64String);
    const bytes = new Uint8Array(binaryString.length);
    for (let i = 0; i < binaryString.length; i++) {
        bytes[i] = binaryString.charCodeAt(i);
    }

    const int16Array = new Int16Array(bytes.buffer);
    const float32Array = new Float32Array(int16Array.length);
    for (let i = 0; i < int16Array.length; i++) {
        float32Array[i] = int16Array[i] / 32768.0;
    }

    return float32Array;
}

/**
 * Converts audio data to base64 encoded string
 * Used for sending audio data to the server
 * @param {ArrayBuffer} buffer - Audio data as ArrayBuffer
 * @returns {string} - Base64 encoded audio data
 */
export function arrayBufferToBase64(buffer) {
    let binary = '';
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < bytes.byteLength; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}