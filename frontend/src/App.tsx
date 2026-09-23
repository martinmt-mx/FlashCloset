import { useState } from "react";
import { getToken } from "./api";
import { DressingRoom } from "./components/DressingRoom";
import { Login } from "./components/Login";

export default function App() {
  const [signedIn, setSignedIn] = useState(Boolean(getToken()));

  return signedIn
    ? <DressingRoom onSignOut={() => setSignedIn(false)} />
    : <Login onDone={() => setSignedIn(true)} />;
}
