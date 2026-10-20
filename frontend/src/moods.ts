/** The moods a status can carry, and how each one is spelled.
 *
 *  Most Spanish adjectives here inflect, so the list stores a stem and lets the
 *  writer pick the ending: contento, contenta, contente. The chosen word is what
 *  gets stored, so a post keeps the spelling its author used no matter who reads
 *  it later, or what ending that reader happens to prefer.
 */

export type Gender = "m" | "f" | "e";

export const GENDERS: { id: Gender; label: string }[] = [
  { id: "m", label: "masculino" },
  { id: "f", label: "femenino" },
  { id: "e", label: "inclusivo" },
];

const ENDING: Record<Gender, string> = { m: "o", f: "a", e: "e" };

type Mood = {
  /** Either the whole word, when it does not inflect, or the part before the ending. */
  stem: string;
  emoji: string;
  inflects?: boolean;
};

const MOODS: Mood[] = [
  { stem: "feliz", emoji: "😄" },
  { stem: "content", emoji: "🙂", inflects: true },
  { stem: "enamorad", emoji: "😍", inflects: true },
  { stem: "emocionad", emoji: "🤩", inflects: true },
  { stem: "tranquil", emoji: "😌", inflects: true },
  { stem: "cansad", emoji: "🥱", inflects: true },
  { stem: "hart", emoji: "😤", inflects: true },
  { stem: "triste", emoji: "😢" },
  { stem: "con frío", emoji: "🥶" },
  { stem: "con hambre", emoji: "🤤" },
  { stem: "bonit", emoji: "💅", inflects: true },
  { stem: "list", emoji: "😎", inflects: true },
];

export function moodWord(mood: Mood, gender: Gender): string {
  return mood.inflects ? mood.stem + ENDING[gender] : mood.stem;
}

export function moodsFor(gender: Gender): string[] {
  return MOODS.map((mood) => moodWord(mood, gender));
}

/** Every spelling of every mood, so a stored word finds its face whichever
 *  ending its author chose. */
const FACE_OF = new Map<string, string>();
for (const mood of MOODS) {
  const forms = mood.inflects
    ? (Object.keys(ENDING) as Gender[]).map((g) => moodWord(mood, g))
    : [mood.stem];
  for (const form of forms) FACE_OF.set(form.toLowerCase(), mood.emoji);
}

export function moodFace(feeling: string | null): string {
  if (!feeling) return "💬";
  return FACE_OF.get(feeling.trim().toLowerCase()) ?? "✨";
}

const REMEMBERED = "flashcloset.gender";

/** A per-reader convenience, so nobody re-picks their endings on every visit.
 *  Browser storage can be unavailable or cleared, so both sides fail quietly. */
export function rememberedGender(): Gender {
  try {
    const saved = localStorage.getItem(REMEMBERED);
    if (saved === "m" || saved === "f" || saved === "e") return saved;
  } catch {
    /* private window, blocked storage: fall through to the default */
  }
  return "f";
}

export function rememberGender(gender: Gender): void {
  try {
    localStorage.setItem(REMEMBERED, gender);
  } catch {
    /* not worth telling anyone: the picker still works for this visit */
  }
}
