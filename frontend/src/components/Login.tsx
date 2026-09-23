import { useState } from "react";
import { api, setToken } from "../api";

export function Login({ onDone }: { onDone: () => void }) {
  const [email, setEmail] = useState("martin@flashcloset.app");
  const [password, setPassword] = useState("");
  const [mode, setMode] = useState<"login" | "register">("login");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = mode === "login"
        ? await api.login(email, password)
        : await api.register(email, password);
      setToken(result.access_token);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo entrar");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="login">
      <h1 className="brand">FlashCloset</h1>
      <form className="panel login__card" onSubmit={submit}>
        <label className="sheet__label">Correo</label>
        <input value={email} onChange={(e) => setEmail(e.target.value)} type="email" required />

        <label className="sheet__label">Contraseña</label>
        <input
          value={password} onChange={(e) => setPassword(e.target.value)}
          type="password" required minLength={8}
        />

        {error && <p className="login__error">{error}</p>}

        <button className="pill" disabled={busy}>
          {busy ? "…" : mode === "login" ? "Entrar" : "Crear cuenta"}
        </button>
        <button
          type="button" className="login__switch"
          onClick={() => setMode(mode === "login" ? "register" : "login")}
        >
          {mode === "login" ? "Crear una cuenta" : "Ya tengo cuenta"}
        </button>
      </form>
    </div>
  );
}
