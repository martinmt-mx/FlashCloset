/** The two vertical rails: categories on the left, the wardrobe on the right.
 *  Both page with chevrons when they hold more than fits, as the originals did. */

import { useEffect, useState } from "react";
import type { Category, ClothingItem } from "../api";
import { mediaUrl } from "../api";
import { play } from "../sound";
import { CATEGORY_ICON, CATEGORY_LABEL } from "./icons";

const PAGE = 5;

interface CategoryRailProps {
  categories: Category[];
  active: Category;
  counts: Record<string, number>;
  onPick: (category: Category) => void;
}

export function CategoryRail({ categories, active, counts, onPick }: CategoryRailProps) {
  return (
    <nav className="rail rail--left" aria-label="Categorías">
      {categories.map((category) => {
        const Icon = CATEGORY_ICON[category];
        return (
          <button
            key={category}
            className={`orb orb--pink ${category === active ? "orb--on" : ""}`}
            onClick={() => { play("select"); onPick(category); }}
            title={`${CATEGORY_LABEL[category]} (${counts[category] ?? 0})`}
            aria-pressed={category === active}
          >
            <Icon />
            {(counts[category] ?? 0) > 0 && <span className="orb__count">{counts[category]}</span>}
          </button>
        );
      })}
    </nav>
  );
}

interface GarmentRailProps {
  items: ClothingItem[];
  wornIds: Set<string>;
  onToggle: (item: ClothingItem) => void;
}

export function GarmentRail({ items, wornIds, onToggle }: GarmentRailProps) {
  const [page, setPage] = useState(0);
  const pages = Math.max(1, Math.ceil(items.length / PAGE));

  // A shorter list after switching category must not leave us on a page that is gone.
  useEffect(() => setPage((current) => Math.min(current, pages - 1)), [pages]);

  const visible = items.slice(page * PAGE, page * PAGE + PAGE);

  return (
    <div className="rail rail--right" aria-label="Prendas">
      <button
        className="chevron chevron--up"
        style={{ ["--tip" as string]: "var(--cyan-2)" }}
        onClick={() => setPage((p) => Math.max(0, p - 1))}
        disabled={page === 0}
        aria-label="Anteriores"
      />

      {visible.map((item) => (
        <button
          key={item.id}
          className={`orb orb--cyan ${wornIds.has(item.id) ? "orb--on" : ""}`}
          onClick={() => onToggle(item)}
          title={item.name ?? "Prenda"}
          aria-pressed={wornIds.has(item.id)}
        >
          {item.thumbnail_image_url ?? item.layer_image_url ? (
            <img
              src={mediaUrl((item.thumbnail_image_url ?? item.layer_image_url)!)}
              alt={item.name ?? ""}
              className="orb__thumb"
            />
          ) : (
            <span className="orb__status">{item.status === "failed" ? "!" : "…"}</span>
          )}
        </button>
      ))}

      {visible.length === 0 && <p className="rail__empty">Vacío</p>}

      <button
        className="chevron chevron--down"
        onClick={() => setPage((p) => Math.min(pages - 1, p + 1))}
        disabled={page >= pages - 1}
        aria-label="Siguientes"
      />
    </div>
  );
}
