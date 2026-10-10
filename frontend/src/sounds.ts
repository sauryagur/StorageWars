const sounds = {
  click: "/sounds/click1.ogg",
  hover: "/sounds/rollover1.ogg",
  select: "/sounds/switch1.ogg",
  success: "/sounds/click2.ogg",
};

const audioCache = new Map<string, HTMLAudioElement>();

function getAudio(name: keyof typeof sounds): HTMLAudioElement {
  const path = sounds[name];

  let audio = audioCache.get(path);

  if (!audio) {
    audio = new Audio(path);
    audio.preload = "auto";
    audioCache.set(path, audio);
  }

  return audio;
}

export function playSound(name: keyof typeof sounds): void {
  const original = getAudio(name);
  const audio = original.cloneNode() as HTMLAudioElement;
  audio.volume = 0.35;

  void audio.play().catch(() => {
    // Browsers may block playback before the first user interaction.
  });
}
