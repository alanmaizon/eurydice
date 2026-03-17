/**
 * AudioWorkletProcessor — PCM capture for Gemini Live.
 *
 * Runs off the main thread. Converts Float32 samples to Int16 PCM and
 * transfers the raw ArrayBuffer to the main thread via MessagePort.
 * The main thread base64-encodes the buffer and sends it to the backend.
 *
 * Target format: PCM 16-bit signed, 16 kHz, mono (matches AudioContext
 * sampleRate set in useAudioCapture.ts).
 */
class PcmProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0]?.[0]
    if (channel?.length) {
      const int16 = new Int16Array(channel.length)
      for (let i = 0; i < channel.length; i++) {
        // Clamp Float32 [-1, 1] → Int16 [-32768, 32767]
        int16[i] = Math.max(-32768, Math.min(32767, channel[i] * 32767))
      }
      // Transfer (zero-copy) the buffer to the main thread
      this.port.postMessage(int16.buffer, [int16.buffer])
    }
    return true // Keep processor alive
  }
}

registerProcessor('pcm-processor', PcmProcessor)
