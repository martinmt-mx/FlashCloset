/** The vestidor: avatar centre stage, categories left, wardrobe right. */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Avatar, Category, ClothingItem, Fit } from "../api";
import { api, clearToken, mediaUrl } from "../api";
import { isMuted, play, setMuted } from "../sound";
import { AdjustSheet } from "./AdjustSheet";
import { AvatarStage, fitOf } from "./AvatarStage";
import { CategoryRail, GarmentRail } from "./Rail";
import { AvatarSheet, CatalogSheet, OutfitSheet } from "./Sheets";
import { CATEGORY_LABEL } from "./icons";

const CATEGORIES: Category[] = ["top", "bottom", "full_body", "outerwear", "shoes", "accessory"];

// Only one garment per slot may be worn; outerwear layers over a top.
const SLOT: Record<Category, string> = {
  top: "torso", full_body: "torso", bottom: "legs",
  shoes: "feet", outerwear: "outer", accessory: "extra",
};

export function DressingRoom({ onSignOut }: { onSignOut: () => void }) {
  const [avatar, setAvatar] = useState<Avatar | null>(null);
  const [items, setItems] = useState<ClothingItem[]>([]);
  const [worn, setWorn] = useState<Record<string, ClothingItem>>({});
  const [category, setCategory] = useState<Category>("top");
  const [adjusting, setAdjusting] = useState<ClothingItem | null>(null);
  const [draft, setDraft] = useState<Fit | null>(null);
  const [opacity, setOpacity] = useState(1);
  const [toast, setToast] = useState<string | null>(null);
  const fileInput = useRef<HTMLInputElement>(null);

  const [avatars, setAvatars] = useState<Avatar[]>([]);
  const [showAvatars, setShowAvatars] = useState(false);
  const [showCatalog, setShowCatalog] = useState(false);
  const [showOutfits, setShowOutfits] = useState(false);
  const [muted, setMutedState] = useState(isMuted());

  const refresh = useCallback(async (avatarId?: string) => {
    const list = await api.avatars();
    setAvatars(list);
    const chosen = list.find((a) => a.id === avatarId) ?? list.find((a) => a.is_default) ?? list[0];
    setAvatar(chosen ?? null);
    const closet = await api.items(chosen?.id);
    setItems(closet);
    return closet;
  }, []);

  useEffect(() => {
    refresh().catch(() => onSignOut());
  }, [refresh, onSignOut]);

  // Anything still generating will change state on its own, so poll while that is true.
  const pending = items.some((i) => i.status === "pending" || i.status === "processing");
  useEffect(() => {
    if (!pending) return;
    const timer = setInterval(() => void refresh(avatar?.id), 4000);
    return () => clearInterval(timer);
  }, [pending, refresh, avatar?.id]);

  function switchAvatar(next: Avatar) {
    setWorn({});
    setShowAvatars(false);
    void refresh(next.id);
    flash(`Ahora vestís a ${next.name}`);
  }

  async function toggleShared(item: ClothingItem) {
    const updated = await api.setShared(item.id, !item.is_shared);
    setItems((current) => current.map((i) => (i.id === updated.id ? updated : i)));
    flash(updated.is_shared ? "Prenda compartida" : "Ya no se comparte");
  }

  const ready = useMemo(
    () => items.filter((i) => i.status === "ready" && i.layer_image_url),
    [items],
  );
  const counts = useMemo(() => {
    const totals: Record<string, number> = {};
    for (const item of items) totals[item.category] = (totals[item.category] ?? 0) + 1;
    return totals;
  }, [items]);

  const shown = useMemo(
    () => items.filter((i) => i.category === category),
    [items, category],
  );
  const wornList = Object.values(worn);
  const wornIds = new Set(wornList.map((i) => i.id));

  function toggle(item: ClothingItem) {
    if (item.status !== "ready" || !item.layer_image_url) {
      play("nope");
      setToast(item.status === "failed" ? "Esa prenda falló al procesarse" : "Todavía se está procesando");
      return;
    }
    // Decide here rather than inside the updater: React calls updaters twice in strict
    // mode to expose side effects, which made every cue fire in pairs.
    const slot = SLOT[item.category];
    const takingOff = worn[slot]?.id === item.id;
    play(takingOff ? "remove" : "wear");

    setWorn((current) => {
      const next = { ...current };
      if (takingOff) delete next[slot];
      else next[slot] = item;
      return next;
    });
  }

  function startAdjust() {
    const item = wornList.at(-1);
    if (!item) return;
    setAdjusting(item);
    setDraft(fitOf(item));
    setOpacity(1);
  }

  async function saveFit() {
    if (!adjusting || !draft) return;
    const saved = await api.saveFit(adjusting.id, draft);
    setItems((current) => current.map((i) => (i.id === saved.id ? saved : i)));
    setWorn((current) =>
      Object.fromEntries(Object.entries(current).map(([k, v]) => [k, v.id === saved.id ? saved : v])),
    );
    setAdjusting(null);
    setDraft(null);
    play("save");
    flash("Calce guardado");
  }

  async function upload(file: File) {
    flash("Subiendo…");
    await api.upload(file, category, file.name.replace(/\.[^.]+$/, ""));
    await refresh(avatar?.id);
    flash("Procesando la prenda, tarda un momento");
  }

  async function saveOutfit() {
    if (wornList.length === 0 || !avatar) return;
    await api.saveOutfit(
      `Look ${new Date().toLocaleDateString()}`,
      avatar.id,
      wornList.map((i) => ({ clothing_item_id: i.id })),
    );
    play("save");
    flash("Look guardado");
  }

  function wearOutfit(chosen: ClothingItem[]) {
    const next: Record<string, ClothingItem> = {};
    for (const item of chosen) next[SLOT[item.category]] = item;
    setWorn(next);
    flash(chosen.length ? "Look puesto" : "Ese look ya no tiene prendas disponibles");
  }

  function flash(message: string) {
    setToast(message);
    setTimeout(() => setToast(null), 2200);
  }

  function openSheet(show: (value: boolean) => void) {
    play("open");
    show(true);
  }

  if (!avatar) return <div className="loading">Cargando el vestidor…</div>;

  return (
    <div className="room">
      <header className="room__bar">
        <h1 className="brand">FlashCloset</h1>
        <div className="room__actions">
          <button className="pill pill--gold" onClick={() => fileInput.current?.click()}>
            + Prenda
          </button>
          <button className="pill pill--cyan" onClick={() => openSheet(setShowCatalog)}>
            Compartidas
          </button>
          <button className="pill pill--cyan" onClick={() => openSheet(setShowAvatars)}>
            {avatar.name}
          </button>
          <button className="pill" onClick={saveOutfit} disabled={wornList.length === 0}>
            Guardar look
          </button>
          <button className="pill pill--gold" onClick={() => openSheet(setShowOutfits)}>
            Mis looks
          </button>
          <button
            className="pill pill--cyan"
            aria-pressed={muted}
            title={muted ? "Activar sonido" : "Silenciar"}
            onClick={() => {
              const next = !muted;
              setMuted(next);
              setMutedState(next);
              if (!next) play("select");
            }}
          >
            {muted ? "Sonido off" : "Sonido on"}
          </button>
          <button className="pill" onClick={() => { clearToken(); onSignOut(); }}>Salir</button>
        </div>
      </header>

      <input
        ref={fileInput} type="file" accept="image/*" hidden
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void upload(file);
          e.target.value = "";
        }}
      />

      <main className="room__main">
        <CategoryRail categories={CATEGORIES} active={category} counts={counts} onPick={setCategory} />

        <section className="room__stage">
          <AvatarStage
            avatarUrl={mediaUrl(avatar.base_image_url)}
            worn={wornList}
            adjustingId={adjusting?.id}
            draftFit={draft}
            opacity={opacity}
          />
          <div className="room__stagebar">
            <button className="pill pill--gold" onClick={startAdjust} disabled={wornList.length === 0}>
              Ajustar
            </button>
            <button
              className="pill"
              disabled={wornList.length === 0}
              onClick={() => wornList.at(-1) && void toggleShared(wornList.at(-1)!)}
            >
              {wornList.at(-1)?.is_shared ? "No compartir" : "Compartir"}
            </button>
            <button className="pill pill--cyan" onClick={() => setWorn({})} disabled={wornList.length === 0}>
              Quitar todo
            </button>
          </div>
        </section>

        <GarmentRail items={shown} wornIds={wornIds} onToggle={toggle} />
      </main>

      <footer className="room__foot">
        {CATEGORY_LABEL[category]} · {shown.length} en el clóset · {ready.length} listas
      </footer>

      <AdjustSheet
        open={Boolean(adjusting)}
        fit={draft ?? { offset_x: 0, offset_y: 0, scale: 1 }}
        onChange={setDraft}
        onSave={() => void saveFit()}
        onCancel={() => { setAdjusting(null); setDraft(null); }}
        opacity={opacity}
        onOpacity={setOpacity}
      />

      <AvatarSheet
        open={showAvatars}
        avatars={avatars}
        activeId={avatar.id}
        onPick={switchAvatar}
        onCreated={() => { setShowAvatars(false); void refresh(); flash("Personaje creado"); }}
        onClose={() => setShowAvatars(false)}
      />

      <OutfitSheet
        open={showOutfits}
        avatarId={avatar.id}
        closet={ready}
        onWear={wearOutfit}
        onClose={() => setShowOutfits(false)}
      />

      <CatalogSheet
        open={showCatalog}
        avatarId={avatar.id}
        onCopied={() => { void refresh(avatar.id); flash("Copiada a tu clóset"); }}
        onClose={() => setShowCatalog(false)}
      />

      <div className={`toast ${toast ? "toast--on" : ""}`}>{toast}</div>
    </div>
  );
}
