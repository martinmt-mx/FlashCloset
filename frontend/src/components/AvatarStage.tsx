/** The avatar with its worn layers.
 *
 *  Layers are sorted by z_index rather than left to the DOM, so "does the jacket sit
 *  over the shirt" is a property of the data and can be reasoned about, not an accident
 *  of render order. Each layer's saved fit is applied as a transform; the PNG is never
 *  rewritten, so an adjustment stays editable forever.
 */

import type { ClothingItem, Fit } from "../api";
import { mediaUrl } from "../api";

interface Props {
  avatarUrl: string;
  worn: ClothingItem[];
  adjustingId?: string | null;
  draftFit?: Fit | null;
  opacity?: number;
}

export function fitOf(item: ClothingItem): Fit {
  return { offset_x: item.offset_x, offset_y: item.offset_y, scale: item.scale };
}

export function AvatarStage({ avatarUrl, worn, adjustingId, draftFit, opacity = 1 }: Props) {
  const layers = [...worn].sort((a, b) => a.z_index - b.z_index);

  return (
    <div className="stage" id="avatar-stage">
      <img className="stage__avatar" src={avatarUrl} alt="Avatar" draggable={false} />
      {layers.map((item) => {
        const fit = item.id === adjustingId && draftFit ? draftFit : fitOf(item);
        return (
          <img
            key={item.id}
            className="stage__layer"
            src={mediaUrl(item.layer_image_url!)}
            alt={item.name ?? ""}
            draggable={false}
            style={{
              zIndex: item.z_index,
              opacity: item.id === adjustingId ? opacity : 1,
              transform: `translate(${fit.offset_x * 100}%, ${fit.offset_y * 100}%) scale(${fit.scale})`,
            }}
          />
        );
      })}
    </div>
  );
}
