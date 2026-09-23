"""Exercise the API end to end against a running server.

    python experiments/api_smoke_test.py

Uses an already-extracted layer to seed a READY garment, so the closet and outfit
endpoints can be tested without spending an image generation.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE = "http://127.0.0.1:8000/api"


def check(label: str, condition: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{f' — {detail}' if detail else ''}")
    return condition


def main() -> int:
    client = httpx.Client(base_url=BASE, timeout=60)
    failures = 0
    email = f"test-{uuid.uuid4().hex[:8]}@flashcloset.app"

    print("auth")
    r = client.post("/auth/register", json={"email": email, "password": "contrasenia123"})
    failures += not check("register returns a token", r.status_code == 201 and "access_token" in r.json())
    token = r.json()["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"

    r = client.post("/auth/register", json={"email": email, "password": "contrasenia123"})
    failures += not check("duplicate email is rejected", r.status_code == 409)

    r = client.post("/auth/login", json={"email": email, "password": "wrongpassword"})
    failures += not check("wrong password is rejected", r.status_code == 401)

    r = httpx.get(f"{BASE}/auth/me")
    failures += not check("unauthenticated request is rejected", r.status_code == 401)

    print("avatar")
    r = client.get("/avatars")
    avatar = r.json()[0]
    failures += not check("default avatar exists with a measured profile",
                          r.status_code == 200 and "body_box" in avatar["profile"],
                          str(avatar["profile"].get("body_box")))

    print("closet")
    photo = ROOT / "assets/garments/camisole_polkadot.webp"
    r = client.post(
        "/clothing-items",
        files={"photo": (photo.name, photo.read_bytes(), "image/webp")},
        data={"category": "top", "name": "camisola de lunares"},
    )
    failures += not check("upload is accepted immediately", r.status_code == 202, f"status={r.json().get('status')}")
    item_id = r.json()["id"]
    failures += not check("z_index defaults by category", r.json()["z_index"] == 20)

    r = client.patch(f"/clothing-items/{item_id}/fit",
                     json={"offset_x": 0.07, "offset_y": -0.04, "scale": 0.93})
    failures += not check("fit is saved on the garment", r.status_code == 200 and r.json()["scale"] == 0.93)

    r = client.patch(f"/clothing-items/{item_id}/fit", json={"offset_x": 9, "offset_y": 0, "scale": 1})
    failures += not check("an out-of-range fit is rejected", r.status_code == 422)

    r = client.get("/clothing-items", params={"category": "shoes"})
    failures += not check("category filter works", r.status_code == 200 and r.json() == [])

    print("outfits")
    r = client.post("/outfits", json={"name": "look de prueba",
                                      "items": [{"clothing_item_id": item_id}]})
    failures += not check("outfit is created", r.status_code == 201, r.text[:80])
    outfit_id = r.json()["id"] if r.status_code == 201 else None

    r = client.post("/outfits", json={"items": [{"clothing_item_id": item_id},
                                                {"clothing_item_id": item_id}]})
    failures += not check("two garments in one slot are rejected", r.status_code in (409, 422))

    r = client.post("/outfits", json={"items": [{"clothing_item_id": str(uuid.uuid4())}]})
    failures += not check("unknown garment is rejected", r.status_code == 404)

    if outfit_id:
        r = client.get(f"/outfits/{outfit_id}")
        failures += not check("outfit round-trips with its items",
                              r.status_code == 200 and len(r.json()["items"]) == 1)
        failures += not check("outfit item inherits the garment's z_index",
                              r.json()["items"][0]["z_index"] == 20)

    print("isolation")
    other = httpx.Client(base_url=BASE, timeout=30)
    r = other.post("/auth/register",
                   json={"email": f"other-{uuid.uuid4().hex[:6]}@flashcloset.app",
                         "password": "contrasenia123"})
    other.headers["Authorization"] = f"Bearer {r.json()['access_token']}"
    r = other.get(f"/clothing-items/{item_id}")
    failures += not check("another user cannot read this garment", r.status_code == 404)

    print("sharing")
    failures += not check("unfinished garments cannot be copied",
                          client.post(f"/clothing-items/{item_id}/copy", json={}).status_code == 409)

    # Sharing needs a finished garment, which only the pipeline (or the seed) produces,
    # so the owner here is the seeded account and the borrower is this test's user.
    owner = httpx.Client(base_url=BASE, timeout=30)
    login = owner.post("/auth/login", json={"email": "martin@flashcloset.app",
                                            "password": "contrasenia123"})
    ready = None
    if login.status_code == 200:
        owner.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        ready = next(
            (i for i in owner.get("/clothing-items").json() if i["status"] == "ready"), None
        )

    if ready is None:
        print("  SKIP  sharing checks need the seeded closet (run seed_closet.py first)")
    else:
        client, other = owner, client  # owner shares, the fresh user borrows
        r = client.patch(f"/clothing-items/{ready['id']}/share", json={"shared": True})
        failures += not check("owner can mark a garment shared", r.status_code == 200 and r.json()["is_shared"])

        r = other.get("/clothing-items/shared/catalog")
        shared_ids = [i["id"] for i in r.json()] if r.status_code == 200 else []
        failures += not check("it shows up in another user's catalog", ready["id"] in shared_ids)

        r = other.post(f"/clothing-items/{ready['id']}/copy", json={})
        failures += not check("another user can copy it", r.status_code == 201, r.text[:70])
        copy = r.json() if r.status_code == 201 else {}
        failures += not check("the copy records its origin", copy.get("source_item_id") == ready["id"])
        failures += not check("the copy reuses the same layer file",
                              copy.get("layer_image_url") == ready["layer_image_url"])

        if copy:
            r = other.patch(f"/clothing-items/{copy['id']}/fit",
                            json={"offset_x": 0.02, "offset_y": 0.01, "scale": 1.05})
            failures += not check("the copy is adjusted independently", r.status_code == 200)
            original = client.get(f"/clothing-items/{ready['id']}").json()
            failures += not check("adjusting the copy left the original untouched",
                                  original["scale"] == ready["scale"])

        r = other.post(f"/clothing-items/{ready['id']}/copy", json={})
        failures += not check("the same garment cannot be copied twice", r.status_code == 409,
                              r.text[:70])

        catalog_again = [i["id"] for i in other.get("/clothing-items/shared/catalog").json()]
        failures += not check("and it disappears from the catalog once owned",
                              ready["id"] not in catalog_again)

        if copy:
            r = other.patch(f"/clothing-items/{copy['id']}/share", json={"shared": True})
            r = client.post(f"/clothing-items/{copy['id']}/copy", json={})
            failures += not check("copying a copy back to the original owner is refused",
                                  r.status_code == 409, r.text[:70])

        r = client.patch(f"/clothing-items/{ready['id']}/share", json={"shared": False})
        r = other.post(f"/clothing-items/{ready['id']}/copy", json={})
        failures += not check("unsharing stops further copies", r.status_code in (404, 409))

    print(f"\n{'all checks passed' if not failures else f'{failures} check(s) failed'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
