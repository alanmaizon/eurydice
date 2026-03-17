/**
 * Minimal WAV encoder.
 * Takes an Int16Array of mono PCM samples and returns a base64-encoded WAV string.
 */
export function encodeWavBase64(pcm: Int16Array, sampleRate: number): string {
  const dataBytes = pcm.byteLength
  const buf = new ArrayBuffer(44 + dataBytes)
  const v = new DataView(buf)

  const str = (offset: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(offset + i, s.charCodeAt(i))
  }

  str(0, "RIFF")
  v.setUint32(4,  36 + dataBytes, true)
  str(8, "WAVE")
  str(12, "fmt ")
  v.setUint32(16, 16, true)          // PCM chunk size
  v.setUint16(20, 1,  true)          // PCM format
  v.setUint16(22, 1,  true)          // mono
  v.setUint32(24, sampleRate, true)
  v.setUint32(28, sampleRate * 2, true)  // byte rate (16-bit mono)
  v.setUint16(32, 2,  true)          // block align
  v.setUint16(34, 16, true)          // bits per sample
  str(36, "data")
  v.setUint32(40, dataBytes, true)

  new Int16Array(buf, 44).set(pcm)

  const bytes = new Uint8Array(buf)
  let bin = ""
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i])
  return btoa(bin)
}
