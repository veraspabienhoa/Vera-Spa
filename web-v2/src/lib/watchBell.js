let audioContext = null

const getAudioContext = () => {
  if (typeof window === 'undefined') return null
  const AudioContextClass = window.AudioContext || window.webkitAudioContext
  if (!AudioContextClass) return null
  if (!audioContext) audioContext = new AudioContextClass()
  return audioContext
}

const addTone = (context, startAt, frequency, duration, volume) => {
  const oscillator = context.createOscillator()
  const gain = context.createGain()
  oscillator.type = 'sine'
  oscillator.frequency.setValueAtTime(frequency, startAt)
  oscillator.frequency.exponentialRampToValueAtTime(frequency * 0.72, startAt + duration)
  gain.gain.setValueAtTime(0.0001, startAt)
  gain.gain.exponentialRampToValueAtTime(volume, startAt + 0.018)
  gain.gain.exponentialRampToValueAtTime(0.0001, startAt + duration)
  oscillator.connect(gain)
  gain.connect(context.destination)
  oscillator.start(startAt)
  oscillator.stop(startAt + duration + 0.03)
}

export const unlockWatchBellAudio = async () => {
  const context = getAudioContext()
  if (!context) return false
  try {
    if (context.state === 'suspended') await context.resume()
    if (context.state !== 'running') return false

    // A nearly silent, short tone unlocks Web Audio during a user gesture on iOS/Safari.
    const oscillator = context.createOscillator()
    const gain = context.createGain()
    gain.gain.value = 0.0001
    oscillator.connect(gain)
    gain.connect(context.destination)
    oscillator.start()
    oscillator.stop(context.currentTime + 0.02)
    return true
  } catch {
    return false
  }
}

export const playWatchBellSound = async () => {
  const context = getAudioContext()
  if (!context) return false
  const ready = await unlockWatchBellAudio()
  if (!ready) return false

  const startAt = context.currentTime + 0.025
  addTone(context, startAt, 1046.5, 0.62, 0.16)
  addTone(context, startAt + 0.18, 1318.5, 0.72, 0.13)
  addTone(context, startAt + 0.46, 1046.5, 0.78, 0.11)
  return true
}
