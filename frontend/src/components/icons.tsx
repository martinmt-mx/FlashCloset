/** Category glyphs, drawn as flat white silhouettes to sit inside the orbs. */

// React 19 no longer publishes a global JSX namespace, so the element type is
// imported rather than assumed.
import type { ReactElement } from "react";

import type { Category } from "../api";

const props = { viewBox: "0 0 24 24", fill: "#fff", width: "56%", height: "56%" };

const Top = () => (
  <svg {...props}>
    <path d="M8.5 3 5 4.8 3 9l2.6 1.4L7 8.6V21h10V8.6l1.4 1.8L21 9l-2-4.2L15.5 3a3.6 3.6 0 0 1-7 0Z" />
  </svg>
);

const Bottom = () => (
  <svg {...props}>
    <path d="M7 3h10l1 6-1.2 12h-3.3L12 11l-1.5 10H7.2L6 9Z" />
  </svg>
);

const Shoes = () => (
  <svg {...props}>
    <path d="M3 15h5l3.2-2.6L13 15h6.2c1.2 0 1.8.8 1.8 2v2H3Z" />
    <path d="M4.5 6h3l.7 6h-3Z" />
  </svg>
);

const Outerwear = () => (
  <svg {...props}>
    <path d="M9 3 4 5.5 2.5 21H9V3Zm6 0v18h6.5L20 5.5 15 3Zm-3.6 0h1.2v18h-1.2Z" />
  </svg>
);

const Accessory = () => (
  <svg {...props}>
    <path d="M6 9h12l1.4 11H4.6Zm3-2a3 3 0 0 1 6 0v2h-2V7a1 1 0 0 0-2 0v2H9Z" />
  </svg>
);

const FullBody = () => (
  <svg {...props}>
    <path d="M8.6 3h6.8l2.1 4-2.3 1.4 1.4 12.6H6.4L7.8 8.4 5.5 7Z" />
  </svg>
);

export const CATEGORY_ICON: Record<Category, () => ReactElement> = {
  top: Top,
  bottom: Bottom,
  shoes: Shoes,
  outerwear: Outerwear,
  accessory: Accessory,
  full_body: FullBody,
};

export const CATEGORY_LABEL: Record<Category, string> = {
  top: "Tops",
  bottom: "Pantalones",
  shoes: "Zapatos",
  outerwear: "Abrigos",
  accessory: "Accesorios",
  full_body: "Vestidos",
};
