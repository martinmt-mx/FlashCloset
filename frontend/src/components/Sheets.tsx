/** The two sheets that sit on top of the vestidor: characters and the shared catalog. */

import { useCallback, useEffect, useRef, useState } from "react";
import type { Avatar, ClothingItem, Outfit } from "../api";
import { api, mediaUrl } from "../api";

interface AvatarSheetProps {
  open: boolean;
  avatars: Avatar[];
  activeId: string | null;
  onPick: (avatar: Avatar) => void;
  onCreated: () => void;
  onClose: () => void;
}

export function AvatarSheet({ open, avatars, activeId, onPick, onCreated, onClose }: AvatarSheetProps) {
  const file = useRef<HTMLInputElement>(null);
  const [mode, setMode] = useState<"generate" | "import">("generate");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function create(photo: File) {
    setBusy(true);
    setError(null);
    try {
      await api.createAvatar(photo, mode, photo.name.replace(/\.[^.]+$/, ""));
      onCreated();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo crear el personaje");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`scrim ${open ? "scrim--open" : ""}`}>
      <div className="sheet panel">
        <div className="sheet__grab" />
        <h2>Personajes</h2>
        <p className="sheet__hint">
          Cada personaje tiene su propio clóset: las prendas se generan sobre su cuerpo,
          así que no se pasan de uno a otro. Podés copiarlas desde las compartidas.
        </p>

        <div className="chooser">
          {avatars.map((avatar) => (
            <button
              key={avatar.id}
              className={`chooser__item ${avatar.id === activeId ? "chooser__item--on" : ""}`}
              onClick={() => onPick(avatar)}
            >
              <img src={mediaUrl(avatar.base_image_url)} alt={avatar.name} />
              <span>{avatar.name}</span>
            </button>
          ))}
        </div>

        <label className="sheet__label">Nuevo personaje</label>
        <div className="sheet__actions">
          <button
            className={`pill ${mode === "generate" ? "" : "pill--cyan"}`}
            onClick={() => setMode("generate")}
          >
            Desde una foto
          </button>
          <button
            className={`pill ${mode === "import" ? "" : "pill--cyan"}`}
            onClick={() => setMode("import")}
          >
            Ya lo tengo
          </button>
        </div>
        <p className="sheet__hint" style={{ marginTop: 10 }}>
          {mode === "generate"
            ? "Subí una foto de cuerpo entero, de frente y con buena luz."
            : "Subí un avatar ya dibujado en la pose del juego."}
        </p>

        {error && <p className="login__error">{error}</p>}

        <input
          ref={file}
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const picked = e.target.files?.[0];
            if (picked) void create(picked);
            e.target.value = "";
          }}
        />

        <div className="sheet__actions">
          <button className="pill pill--cyan" onClick={onClose}>Cerrar</button>
          <button className="pill pill--gold" disabled={busy} onClick={() => file.current?.click()}>
            {busy ? "Creando…" : "Elegir foto"}
          </button>
        </div>
      </div>
    </div>
  );
}

interface OutfitSheetProps {
  open: boolean;
  avatarId: string | null;
  closet: ClothingItem[];
  onWear: (items: ClothingItem[]) => void;
  onClose: () => void;
}

export function OutfitSheet({ open, avatarId, closet, onWear, onClose }: OutfitSheetProps) {
  const [outfits, setOutfits] = useState<Outfit[]>([]);

  const load = useCallback(() => {
    api.outfits()
      .then((all) => setOutfits(all.filter((o) => o.avatar_id === avatarId)))
      .catch(() => setOutfits([]));
  }, [avatarId]);

  useEffect(() => {
    if (open) load();
  }, [open, load]);

  function wear(outfit: Outfit) {
    // A look may name garments that were since deleted, so resolve against the closet
    // and wear whatever still exists rather than failing the whole thing.
    const found = outfit.items
      .map((entry) => closet.find((item) => item.id === entry.clothing_item_id))
      .filter((item): item is ClothingItem => Boolean(item));
    onWear(found);
    onClose();
  }

  async function remove(outfit: Outfit) {
    await api.deleteOutfit(outfit.id);
    load();
  }

  return (
    <div className={`scrim ${open ? "scrim--open" : ""}`}>
      <div className="sheet panel">
        <div className="sheet__grab" />
        <h2>Looks guardados</h2>
        <p className="sheet__hint">De este personaje. Tocá uno para ponérselo.</p>

        {outfits.length === 0 ? (
          <p className="sheet__hint">Todavía no guardaste ningún look.</p>
        ) : (
          <ul className="looks">
            {outfits.map((outfit) => (
              <li key={outfit.id} className="looks__row">
                <button className="looks__wear" onClick={() => wear(outfit)}>
                  <span className="looks__name">{outfit.name ?? "Sin nombre"}</span>
                  <span className="looks__count">{outfit.items.length} prendas</span>
                </button>
                <button
                  className="looks__delete"
                  onClick={() => void remove(outfit)}
                  aria-label={`Borrar ${outfit.name ?? "look"}`}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="sheet__actions">
          <button className="pill pill--cyan" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}

interface CatalogSheetProps {
  open: boolean;
  avatarId: string | null;
  onCopied: () => void;
  onClose: () => void;
}

export function CatalogSheet({ open, avatarId, onCopied, onClose }: CatalogSheetProps) {
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    api.sharedCatalog(avatarId ?? undefined).then(setItems).catch(() => setItems([]));
  }, [open, avatarId]);

  async function copy(item: ClothingItem) {
    setBusyId(item.id);
    setError(null);
    try {
      await api.copyToCloset(item.id, avatarId ?? undefined);
      // Drop it from the list straight away: it now lives in this closet and the
      // server will refuse a second copy anyway.
      setItems((current) => current.filter((i) => i.id !== item.id));
      onCopied();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo copiar");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className={`scrim ${open ? "scrim--open" : ""}`}>
      <div className="sheet panel">
        <div className="sheet__grab" />
        <h2>Prendas compartidas</h2>
        <p className="sheet__hint">
          Al copiarlas obtenés tu propia versión, con su ajuste independiente. Como fueron
          hechas sobre otro cuerpo pueden no calzar perfecto: se corrigen con Ajustar.
        </p>

        {items.length === 0 ? (
          <p className="sheet__hint">
            No hay nada para agregar: este personaje ya tiene todas las prendas
            disponibles, tuyas y compartidas.
          </p>
        ) : (
          <div className="chooser">
            {items.map((item) => (
              <button
                key={item.id}
                className="chooser__item"
                disabled={busyId === item.id}
                onClick={() => void copy(item)}
              >
                <img
                  src={mediaUrl((item.thumbnail_image_url ?? item.layer_image_url)!)}
                  alt={item.name ?? ""}
                />
                <span>{busyId === item.id ? "Copiando…" : item.name ?? "Prenda"}</span>
              </button>
            ))}
          </div>
        )}

        {error && <p className="login__error">{error}</p>}

        <div className="sheet__actions">
          <button className="pill pill--cyan" onClick={onClose}>Cerrar</button>
        </div>
      </div>
    </div>
  );
}
