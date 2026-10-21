/** The public wall: TheSlap's "Right Now" board, in glass and water.
 *
 *  Anyone with the link reads it; only the two accounts write. There is nothing
 *  to react with on purpose, so a status carries only words, a picture and a mood.
 */

import { useEffect, useMemo, useState } from "react";
import { api, getToken, type Post } from "../api";
import { moodFace } from "../moods";
import { Composer } from "./Composer";

/** Wall clocks read in glances, so anything older than a week is just the date. */
function when(iso: string): string {
  // Timestamps arrive naive from the API; they are UTC, so say so before parsing.
  const then = new Date(/[Zz+]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`);
  const mins = Math.round((Date.now() - then.getTime()) / 60000);
  if (!Number.isFinite(mins)) return "";
  if (mins < 1) return "ahorita";
  if (mins < 60) return `hace ${mins} min`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.round(hours / 24);
  if (days < 7) return `hace ${days} d`;
  return then.toLocaleDateString("es-MX", { day: "numeric", month: "long" });
}

function Bubbles() {
  // Fixed seeds rather than random so the field does not reshuffle on every render.
  const bubbles = useMemo(
    () => [
      { left: 6, size: 46, dur: 23, delay: 0, drift: 26 },
      { left: 19, size: 20, dur: 17, delay: 4, drift: -18 },
      { left: 33, size: 62, dur: 29, delay: 9, drift: 32 },
      { left: 47, size: 15, dur: 14, delay: 2, drift: -12 },
      { left: 61, size: 38, dur: 21, delay: 7, drift: 22 },
      { left: 74, size: 26, dur: 19, delay: 12, drift: -24 },
      { left: 88, size: 54, dur: 26, delay: 5, drift: 18 },
      { left: 95, size: 18, dur: 16, delay: 15, drift: -10 },
    ],
    [],
  );
  return (
    <div className="aero__bubbles" aria-hidden="true">
      {bubbles.map((b, i) => (
        <span
          key={i}
          className="aero__bubble"
          style={{
            left: `${b.left}%`,
            width: b.size,
            height: b.size,
            animationDuration: `${b.dur}s`,
            animationDelay: `${b.delay}s`,
            ["--drift" as string]: `${b.drift}px`,
          }}
        />
      ))}
    </div>
  );
}

function Status({ post, onDelete }: { post: Post; onDelete?: () => void }) {
  return (
    <article className="panel">
      <span className="panel__tab">{post.author}</span>
      <div className="panel__body">
        <div className="status">
          <div className="status__main">
            <p className="status__when">{when(post.created_at)}</p>
            {post.body && <p className="status__body">{post.body}</p>}
            {post.image_url && (
              <img className="status__photo" src={post.image_url} alt="" loading="lazy" />
            )}
            <div className="compose__row">
              {post.feeling && (
                <span className="status__mood">
                  <span aria-hidden="true">{moodFace(post.feeling)}</span>
                  Estado: <b>{post.feeling}</b>
                </span>
              )}
              {onDelete && (
                <button className="gel gel--sm status__drop" onClick={onDelete}>
                  Borrar
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </article>
  );
}

export function Wall({ onEnter }: { onEnter: () => void }) {
  const [posts, setPosts] = useState<Post[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Posts carry only the author's display name, because the wall is public and
  // nothing else about an account belongs in it. Matching that name is therefore
  // how the page knows which posts are the reader's own to delete.
  const [me, setMe] = useState<string | null>(null);
  const signedIn = Boolean(getToken());

  async function load() {
    try {
      setPosts(await api.posts());
    } catch {
      setError("No se pudo cargar el muro. Puede que el servidor esté despertando.");
    }
  }

  useEffect(() => {
    void load();
    if (!signedIn) return;
    api
      .me()
      .then((user) => setMe(user.display_name || user.email.split("@")[0]))
      .catch(() => setMe(null));
  }, [signedIn]);

  async function remove(id: string) {
    await api.deletePost(id);
    setPosts((current) => (current ?? []).filter((p) => p.id !== id));
  }

  return (
    <div className="aero">
      <Bubbles />
      <div className="aero__inner">
        <header className="aero__bar">
          <h1 className="aero__logo">
            Flash<span>Closet</span>
          </h1>
          <button className="gel gel--sun" onClick={onEnter}>
            {signedIn ? "Mi clóset" : "Entrar"}
          </button>
        </header>

        {signedIn && <Composer onPosted={(p) => setPosts((c) => [p, ...(c ?? [])])} />}

        {error && <p className="aero__error">{error}</p>}

        {posts === null && !error && <p className="aero__empty">Cargando…</p>}

        {posts?.length === 0 && (
          <section className="panel">
            <span className="panel__tab panel__tab--leaf">Ahora mismo</span>
            <div className="panel__body">
              <p className="aero__empty">
                Todavía no hay nada por aquí.
                {!signedIn && " Vuelve al rato."}
              </p>
            </div>
          </section>
        )}

        {posts?.map((post) => (
          <Status
            key={post.id}
            post={post}
            onDelete={me && post.author === me ? () => void remove(post.id) : undefined}
          />
        ))}
      </div>
    </div>
  );
}
