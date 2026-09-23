/** Interface sounds.
 *
 *  Browsers refuse to play audio before the page has been interacted with, so nothing
 *  is decoded until the first gesture. Every sound here follows a click anyway, which
 *  is why none of this needs an autoplay workaround.
 */

export type Cue = "select" | "wear" | "remove" | "save" | "open" | "nope";

const MUTE_KEY = "flashcloset.muted";
const FILES: Cue[] = ["select", "wear", "remove", "save", "open", "nope"];

let context: AudioContext | null = null;
const buffers = new Map<Cue, AudioBuffer>();
let loading: Promise<void> | null = null;

export function isMuted(): boolean {
  try {
    return localStorage.getItem(MUTE_KEY) === "1";
  } catch {
    return false;
  }
}

export function setMuted(muted: boolean): void {
  try {
    localStorage.setItem(MUTE_KEY, muted ? "1" : "0");
  } catch {
    /* private mode: the preference just will not survive a reload */
  }
}

async function ready(): Promise<void> {
  if (!context) context = new AudioContext();
  if (context.state === "suspended") await context.resume();

  if (!loading) {
    loading = Promise.all(
      FILES.map(async (cue) => {
        const response = await fetch(`/sounds/${cue}.wav`);
        buffers.set(cue, await context!.decodeAudioData(await response.arrayBuffer()));
      }),
    ).then(() => undefined);
  }
  return loading;
}

export function play(cue: Cue, volume = 0.5): void {
  if (isMuted()) return;

  void ready()
    .then(() => {
      const buffer = buffers.get(cue);
      if (!buffer || !context) return;

      const source = context.createBufferSource();
      const gain = context.createGain();
      source.buffer = buffer;
      gain.gain.value = volume;
      source.connect(gain).connect(context.destination);
      source.start();
    })
    .catch(() => {
      /* audio is a garnish: never let it break an interaction */
    });
}
