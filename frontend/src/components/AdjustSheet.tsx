/** Fit adjustment, hidden behind a button because it is the exception, not the routine.
 *
 *  The sheet never takes pointer events while closed: it sits over the rails, and an
 *  invisible panel that still swallows taps is a bug that is hard to see.
 */

import { useEffect, useRef } from "react";
import type { Fit } from "../api";

interface Props {
  open: boolean;
  fit: Fit;
  onChange: (fit: Fit) => void;
  onSave: () => void;
  onCancel: () => void;
  opacity: number;
  onOpacity: (value: number) => void;
}

export function AdjustSheet({ open, fit, onChange, onSave, onCancel, opacity, onOpacity }: Props) {
  const dragging = useRef<{ x: number; y: number; fit: Fit } | null>(null);

  useEffect(() => {
    if (!open) return;

    const stage = document.getElementById("avatar-stage");
    if (!stage) return;

    const down = (event: PointerEvent) => {
      dragging.current = { x: event.clientX, y: event.clientY, fit };
      stage.setPointerCapture(event.pointerId);
    };
    const move = (event: PointerEvent) => {
      const start = dragging.current;
      if (!start) return;
      const box = stage.getBoundingClientRect();
      onChange({
        ...start.fit,
        offset_x: start.fit.offset_x + (event.clientX - start.x) / box.width,
        offset_y: start.fit.offset_y + (event.clientY - start.y) / box.height,
      });
    };
    const up = () => {
      dragging.current = null;
    };
    const wheel = (event: WheelEvent) => {
      event.preventDefault();
      onChange({ ...fit, scale: clamp(fit.scale - event.deltaY * 0.0012, 0.5, 1.6) });
    };
    const key = (event: KeyboardEvent) => {
      if (event.key === "Escape") return onCancel();
      const step = event.shiftKey ? 10 : 1;
      const moves: Record<string, [number, number]> = {
        ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step],
      };
      const delta = moves[event.key];
      if (!delta) return;
      event.preventDefault();
      const box = stage.getBoundingClientRect();
      onChange({
        ...fit,
        offset_x: fit.offset_x + delta[0] / box.width,
        offset_y: fit.offset_y + delta[1] / box.height,
      });
    };

    stage.addEventListener("pointerdown", down);
    stage.addEventListener("pointermove", move);
    stage.addEventListener("pointerup", up);
    stage.addEventListener("pointercancel", up);
    stage.addEventListener("wheel", wheel, { passive: false });
    window.addEventListener("keydown", key);
    stage.classList.add("stage--adjusting");

    return () => {
      stage.removeEventListener("pointerdown", down);
      stage.removeEventListener("pointermove", move);
      stage.removeEventListener("pointerup", up);
      stage.removeEventListener("pointercancel", up);
      stage.removeEventListener("wheel", wheel);
      window.removeEventListener("keydown", key);
      stage.classList.remove("stage--adjusting");
    };
  }, [open, fit, onChange, onCancel]);

  return (
    <div className={`scrim ${open ? "scrim--open" : ""}`}>
      <div className="sheet panel">
        <div className="sheet__grab" />
        <h2>Ajustar calce</h2>
        <p className="sheet__hint">Arrastrá la prenda sobre el avatar. La rueda cambia el tamaño.</p>

        <label className="sheet__label">Tamaño</label>
        <input
          type="range" min={0.5} max={1.6} step={0.002} value={fit.scale}
          onChange={(e) => onChange({ ...fit, scale: Number(e.target.value) })}
        />

        <label className="sheet__label">Transparencia</label>
        <input
          type="range" min={0.3} max={1} step={0.01} value={opacity}
          onChange={(e) => onOpacity(Number(e.target.value))}
        />

        <div className="sheet__actions">
          <button className="pill pill--cyan" onClick={onCancel}>Cancelar</button>
          <button className="pill" onClick={onSave}>Guardar</button>
        </div>
      </div>
    </div>
  );
}

const clamp = (value: number, min: number, max: number) => Math.min(max, Math.max(min, value));
