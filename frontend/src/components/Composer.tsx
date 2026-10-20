/** The posting box. Rendered only for a signed-in visitor, and the API refuses
 *  the write anyway, so the wall stays read-only for everyone else. */

import { useRef, useState } from "react";
import { api, type Post } from "../api";
import { moodFace } from "./Wall";

const MOODS = [
  "feliz", "contenta", "enamorada", "emocionada",
  "tranquila", "cansada", "harta", "triste",
  "con frío", "con hambre", "bonita", "lista",
];

const MAX = 500;

export function Composer({ onPosted }: { onPosted: (post: Post) => void }) {
  const [body, setBody] = useState("");
  const [feeling, setFeeling] = useState<string | null>(null);
  const [photo, setPhoto] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  function pick(file: File | null) {
    setPhoto(file);
    // Revoking the old object URL keeps a long session from leaking blobs.
    setPreview((old) => {
      if (old) URL.revokeObjectURL(old);
      return file ? URL.createObjectURL(file) : null;
    });
  }

  async function send() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const post = await api.createPost(body.trim(), feeling, photo);
      onPosted(post);
      setBody("");
      setFeeling(null);
      pick(null);
      if (fileInput.current) fileInput.current.value = "";
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo publicar");
    } finally {
      setBusy(false);
    }
  }

  const empty = !body.trim() && !photo;

  return (
    <section className="panel">
      <span className="panel__tab panel__tab--sun">Escribe algo</span>
      <div className="panel__body">
        {error && <p className="aero__error">{error}</p>}

        <textarea
          className="compose__field"
          rows={3}
          maxLength={MAX}
          placeholder="¿Qué está pasando?"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />

        <div className="compose__moods">
          {MOODS.map((mood) => (
            <button
              key={mood}
              type="button"
              className="compose__mood"
              aria-pressed={feeling === mood}
              onClick={() => setFeeling(feeling === mood ? null : mood)}
            >
              <span aria-hidden="true">{moodFace(mood)}</span> {mood}
            </button>
          ))}
        </div>

        {preview && <img className="compose__preview" src={preview} alt="" />}

        <div className="compose__row">
          <input
            ref={fileInput}
            id="wall-photo"
            type="file"
            accept="image/*"
            hidden
            onChange={(e) => pick(e.target.files?.[0] ?? null)}
          />
          <button
            type="button"
            className="gel gel--sm"
            onClick={() => fileInput.current?.click()}
          >
            {photo ? "Cambiar foto" : "Subir foto"}
          </button>
          {photo && (
            <button type="button" className="gel gel--sm" onClick={() => pick(null)}>
              Quitar
            </button>
          )}
          <span className="compose__count">
            {body.length}/{MAX}
          </span>
          <button
            className="gel gel--leaf"
            onClick={() => void send()}
            disabled={busy || empty}
          >
            {busy ? "Publicando…" : "Publicar"}
          </button>
        </div>
      </div>
    </section>
  );
}
