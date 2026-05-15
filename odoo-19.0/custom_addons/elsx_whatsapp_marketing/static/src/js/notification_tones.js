/** @odoo-module **/

let audioContext;

const TONES = {
    bell: [
        { frequency: 880, duration: 0.16, type: 'sine', gain: 1 },
        { frequency: 1320, duration: 0.18, type: 'sine', gain: 0.65, delay: 0.08 },
    ],
    chime: [
        { frequency: 523.25, duration: 0.12, type: 'sine', gain: 0.75 },
        { frequency: 659.25, duration: 0.12, type: 'sine', gain: 0.7, delay: 0.12 },
        { frequency: 783.99, duration: 0.18, type: 'sine', gain: 0.65, delay: 0.24 },
    ],
    pop: [
        { frequency: 460, endFrequency: 210, duration: 0.12, type: 'triangle', gain: 0.9 },
    ],
    ting: [
        { frequency: 1174.66, duration: 0.14, type: 'sine', gain: 0.9 },
        { frequency: 1567.98, duration: 0.1, type: 'sine', gain: 0.45, delay: 0.03 },
    ],
    swish: [
        { frequency: 320, endFrequency: 960, duration: 0.18, type: 'sawtooth', gain: 0.4 },
        { frequency: 760, endFrequency: 1320, duration: 0.15, type: 'triangle', gain: 0.35, delay: 0.06 },
    ],
    click: [
        { frequency: 1400, duration: 0.035, type: 'square', gain: 0.55 },
        { frequency: 900, duration: 0.025, type: 'square', gain: 0.35, delay: 0.025 },
    ],
};

function getAudioContext() {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!AudioContext) {
        return null;
    }
    audioContext = audioContext || new AudioContext();
    return audioContext;
}

function scheduleTone(context, type, toneName) {
    const tone = TONES[toneName];
    if (!tone) {
        return;
    }

    const baseVolume = type === 'sent' ? 0.12 : 0.16;
    const startAt = context.currentTime + 0.01;

    for (const note of tone) {
        const oscillator = context.createOscillator();
        const gain = context.createGain();
        const delay = note.delay || 0;
        const start = startAt + delay;
        const end = start + note.duration;

        oscillator.type = note.type;
        oscillator.frequency.setValueAtTime(note.frequency, start);
        if (note.endFrequency) {
            oscillator.frequency.exponentialRampToValueAtTime(note.endFrequency, end);
        }

        gain.gain.setValueAtTime(0.0001, start);
        gain.gain.linearRampToValueAtTime(baseVolume * note.gain, start + 0.012);
        gain.gain.exponentialRampToValueAtTime(0.0001, end);

        oscillator.connect(gain);
        gain.connect(context.destination);
        oscillator.start(start);
        oscillator.stop(end + 0.02);
    }
}

export function playTone(type, toneName) {
    if (!toneName || toneName === 'none') {
        return;
    }

    const context = getAudioContext();
    if (!context) {
        return;
    }

    if (context.state === 'suspended') {
        context.resume()
            .then(() => scheduleTone(context, type, toneName))
            .catch((error) => console.warn('[WhatsApp] Sound blocked by browser policy:', error));
        return;
    }

    console.log(`[WhatsApp] Playing tone: ${toneName} (${type})`);
    scheduleTone(context, type, toneName);
}
