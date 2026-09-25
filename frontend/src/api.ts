/** Thin client over the FlashCloset API. */

export type Category = "top" | "bottom" | "shoes" | "outerwear" | "accessory" | "full_body";
export type Status = "pending" | "processing" | "ready" | "failed";

export interface ClothingItem {
  id: string;
  name: string | null;
  category: Category;
  z_index: number;
  status: Status;
  error: string | null;
  original_image_url: string;
  layer_image_url: string | null;
  preview_image_url: string | null;
  thumbnail_image_url: string | null;
  offset_x: number;
  offset_y: number;
  scale: number;
  // The backend has always sent these two; the interface had simply never caught up,
  // which the type check would have said if the build had ever run it.
  is_shared: boolean;
  source_item_id: string | null;
  created_at: string;
}

export interface Avatar {
  id: string;
  name: string;
  base_image_url: string;
  is_default: boolean;
  profile: { size?: [number, number]; body_box?: number[]; background?: number[] };
}

export interface Fit {
  offset_x: number;
  offset_y: number;
  scale: number;
}

export interface OutfitItem {
  clothing_item_id: string;
  z_index: number;
  offset_x: number | null;
  offset_y: number | null;
  scale: number | null;
}

export interface Outfit {
  id: string;
  name: string | null;
  avatar_id: string;
  is_favorite: boolean;
  created_at: string;
  items: OutfitItem[];
}

// Built for production the app is served by the API itself, so same-origin is right.
// The Vite dev server runs on its own port, so point it at the API there.
const API =
  import.meta.env.VITE_API_URL ??
  (location.port === "5173" ? "http://127.0.0.1:8000" : "");
const TOKEN_KEY = "flashcloset.token";

export const mediaUrl = (path: string) => (path.startsWith("http") ? path : `${API}${path}`);

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

class ApiError extends Error {
  // Declared rather than a constructor parameter property: the latter emits code, so
  // it is rejected under erasableSyntaxOnly, which this project builds with.
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }

  const response = await fetch(`${API}/api${path}`, { ...init, headers });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}));
    throw new ApiError(response.status, detail?.detail?.toString?.() ?? response.statusText);
  }
  return response.status === 204 ? (undefined as T) : ((await response.json()) as T);
}

export const api = {
  health: () =>
    request<{ status: string; image_backend: string; registration: boolean }>("/health"),

  login: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  register: (email: string, password: string) =>
    request<{ access_token: string }>("/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  me: () => request<{ id: string; email: string; display_name: string | null }>("/auth/me"),

  avatars: () => request<Avatar[]>("/avatars"),

  createAvatar: (photo: File, mode: "generate" | "import", name: string) => {
    const form = new FormData();
    form.append("photo", photo);
    form.append("mode", mode);
    form.append("name", name);
    return request<Avatar>("/avatars", { method: "POST", body: form });
  },

  items: (avatarId?: string) =>
    request<ClothingItem[]>(`/clothing-items${avatarId ? `?avatar_id=${avatarId}` : ""}`),

  sharedCatalog: (avatarId?: string) =>
    request<ClothingItem[]>(
      `/clothing-items/shared/catalog${avatarId ? `?avatar_id=${avatarId}` : ""}`,
    ),

  setShared: (id: string, shared: boolean) =>
    request<ClothingItem>(`/clothing-items/${id}/share`, {
      method: "PATCH",
      body: JSON.stringify({ shared }),
    }),

  copyToCloset: (id: string, avatarId?: string) =>
    request<ClothingItem>(`/clothing-items/${id}/copy`, {
      method: "POST",
      body: JSON.stringify({ avatar_id: avatarId ?? null }),
    }),

  upload: (photo: File, category: Category, name: string) => {
    const form = new FormData();
    form.append("photo", photo);
    form.append("category", category);
    if (name) form.append("name", name);
    return request<ClothingItem>("/clothing-items", { method: "POST", body: form });
  },

  saveFit: (id: string, fit: Fit) =>
    request<ClothingItem>(`/clothing-items/${id}/fit`, {
      method: "PATCH",
      body: JSON.stringify(fit),
    }),

  reprocess: (id: string) =>
    request<ClothingItem>(`/clothing-items/${id}/reprocess`, { method: "POST" }),

  remove: (id: string) => request<void>(`/clothing-items/${id}`, { method: "DELETE" }),

  saveOutfit: (name: string, avatarId: string, items: { clothing_item_id: string }[]) =>
    request<Outfit>("/outfits", {
      method: "POST",
      body: JSON.stringify({ name, avatar_id: avatarId, items }),
    }),

  outfits: () => request<Outfit[]>("/outfits"),

  deleteOutfit: (id: string) => request<void>(`/outfits/${id}`, { method: "DELETE" }),
};
