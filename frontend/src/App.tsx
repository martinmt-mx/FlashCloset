import { useEffect, useState } from "react";
import { getToken } from "./api";
import { DressingRoom } from "./components/DressingRoom";
import { Login } from "./components/Login";
import { Wall } from "./components/Wall";

/** The wall is the front door and needs no account; the closet is behind one.
 *  The view lives in the hash so a reload, a back button or a shared link all
 *  land where the reader expects, without pulling in a router. */
type View = "wall" | "closet";

const viewFromHash = (): View => (location.hash === "#closet" ? "closet" : "wall");

export default function App() {
  const [view, setView] = useState<View>(viewFromHash);
  const [signedIn, setSignedIn] = useState(Boolean(getToken()));

  // The two views want opposite things from the document: one scrolls, one does
  // not. The stylesheet keys off this rather than each component fighting body.
  useEffect(() => {
    document.body.dataset.view = view;
  }, [view]);

  useEffect(() => {
    const sync = () => setView(viewFromHash());
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);

  function go(next: View) {
    location.hash = next === "closet" ? "#closet" : "";
    setView(next);
  }

  if (view === "wall") return <Wall onEnter={() => go("closet")} />;

  if (!signedIn) {
    return (
      <Login
        onDone={() => setSignedIn(true)}
        onBack={() => go("wall")}
      />
    );
  }

  return (
    <DressingRoom
      onSignOut={() => {
        setSignedIn(false);
        go("wall");
      }}
      onWall={() => go("wall")}
    />
  );
}
