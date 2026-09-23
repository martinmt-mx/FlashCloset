"""Run the two pipeline passes on a local ComfyUI instance with FLUX.1 Kontext.

Same contract as the Gemini dresser, so the pipeline cannot tell them apart. Kontext
wants short, direct instructions rather than Gemini's numbered rule lists, so it has
its own prompts.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import httpx

from app.services.image_generation import _COVERAGE, Category, DressResult

_DRESS_PROMPT = (
    "Dress the woman in the {description} from the second reference image, worn on "
    "{coverage}. Keep her exact pose, body shape, proportions, face, hair and framing "
    "unchanged, and keep the flat grey background. Same illustrated cel-shaded art style "
    "with bold outlines."
)

_MATTE_PROMPT = (
    "Recolor only the {description} to flat solid magenta, filling it completely with "
    "that one color, no shading. Keep everything else in the image unchanged: the "
    "background, her skin, her body, her face and her hair keep their original colors."
)


@dataclass(frozen=True)
class KontextModels:
    unet: str = "flux1-kontext-dev-Q4_K_S.gguf"
    clip_l: str = "clip_l.safetensors"
    t5: str = "t5xxl_fp8_e4m3fn.safetensors"
    vae: str = "ae.safetensors"


@dataclass(frozen=True)
class SamplerSettings:
    steps: int = 20
    guidance: float = 2.5
    seed: int | None = None  # None draws a fresh seed per call


class ComfyKontextDresser:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8188",
        models: KontextModels = KontextModels(),
        sampler: SamplerSettings = SamplerSettings(),
        timeout_s: float = 1800,
    ) -> None:
        self._http = httpx.Client(base_url=base_url, timeout=60)
        self._models = models
        self._sampler = sampler
        self._timeout_s = timeout_s
        self._client_id = uuid.uuid4().hex

    def dress(
        self, avatar_path: Path, garment_path: Path, category: Category, description: str
    ) -> DressResult:
        avatar = self._upload(avatar_path.read_bytes(), avatar_path.name)
        garment = self._upload(garment_path.read_bytes(), garment_path.name)
        prompt = _DRESS_PROMPT.format(description=description, coverage=_COVERAGE[category])
        return self._run(prompt, [avatar, garment])

    def matte(self, dressed: DressResult, description: str) -> DressResult:
        name = self._upload(dressed.image_bytes, f"dressed-{uuid.uuid4().hex[:8]}.png")
        return self._run(_MATTE_PROMPT.format(description=description), [name])

    def compose(self, prompt: str, images: list[Path]) -> DressResult:
        """Free-form generation from reference images, used to build an avatar."""
        return self._run(prompt, [self._upload(p.read_bytes(), p.name) for p in images])

    # --- ComfyUI plumbing -------------------------------------------------

    def _upload(self, data: bytes, filename: str) -> str:
        response = self._http.post(
            "/upload/image",
            files={"image": (filename, data)},
            data={"overwrite": "true"},
        )
        response.raise_for_status()
        return response.json()["name"]

    def _run(self, prompt: str, images: list[str]) -> DressResult:
        workflow = self._workflow(prompt, images)
        response = self._http.post(
            "/prompt", json={"prompt": workflow, "client_id": self._client_id}
        )
        if response.status_code != 200:
            raise RuntimeError(f"ComfyUI rejected the workflow: {response.text}")
        prompt_id = response.json()["prompt_id"]

        outputs = self._wait_for(prompt_id)
        image = outputs["save"]["images"][0]
        data = self._http.get(
            "/view",
            params={"filename": image["filename"], "subfolder": image["subfolder"],
                    "type": image["type"]},
        ).content
        return DressResult(
            image_bytes=data, mime_type="image/png",
            model=f"kontext:{self._models.unet}", text_response=None,
        )

    def _wait_for(self, prompt_id: str) -> dict:
        deadline = time.monotonic() + self._timeout_s
        while time.monotonic() < deadline:
            history = self._http.get(f"/history/{prompt_id}").json()
            entry = history.get(prompt_id)
            if entry:
                status = entry.get("status", {})
                if status.get("status_str") == "error":
                    raise RuntimeError(f"ComfyUI failed: {status.get('messages')}")
                if entry.get("outputs"):
                    return entry["outputs"]
            time.sleep(2)
        raise TimeoutError(f"ComfyUI did not finish prompt {prompt_id} in {self._timeout_s}s")

    def _workflow(self, prompt: str, images: list[str]) -> dict:
        """API-format graph. The first image is the canvas being edited; every image
        is also chained in as a reference latent so the model can see it."""
        m, s = self._models, self._sampler
        seed = s.seed if s.seed is not None else int.from_bytes(uuid.uuid4().bytes[:6], "big")

        graph: dict[str, dict] = {
            "unet": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": m.unet}},
            "clip": {"class_type": "DualCLIPLoader",
                     "inputs": {"clip_name1": m.clip_l, "clip_name2": m.t5, "type": "flux"}},
            "vae": {"class_type": "VAELoader", "inputs": {"vae_name": m.vae}},
            "text": {"class_type": "CLIPTextEncode",
                     "inputs": {"text": prompt, "clip": ["clip", 0]}},
        }

        conditioning: list = ["text", 0]
        for i, name in enumerate(images):
            graph[f"load{i}"] = {"class_type": "LoadImage", "inputs": {"image": name}}
            graph[f"scale{i}"] = {"class_type": "FluxKontextImageScale",
                                  "inputs": {"image": [f"load{i}", 0]}}
            graph[f"enc{i}"] = {"class_type": "VAEEncode",
                                "inputs": {"pixels": [f"scale{i}", 0], "vae": ["vae", 0]}}
            graph[f"ref{i}"] = {"class_type": "ReferenceLatent",
                                "inputs": {"conditioning": conditioning, "latent": [f"enc{i}", 0]}}
            conditioning = [f"ref{i}", 0]

        graph.update({
            "guidance": {"class_type": "FluxGuidance",
                         "inputs": {"conditioning": conditioning, "guidance": s.guidance}},
            "negative": {"class_type": "ConditioningZeroOut",
                         "inputs": {"conditioning": ["text", 0]}},
            "sample": {"class_type": "KSampler", "inputs": {
                "model": ["unet", 0], "seed": seed, "steps": s.steps, "cfg": 1.0,
                "sampler_name": "euler", "scheduler": "simple",
                "positive": ["guidance", 0], "negative": ["negative", 0],
                # The canvas's own latent fixes the output size to the edited image.
                "latent_image": ["enc0", 0], "denoise": 1.0,
            }},
            "decode": {"class_type": "VAEDecode",
                       "inputs": {"samples": ["sample", 0], "vae": ["vae", 0]}},
            "save": {"class_type": "SaveImage",
                     "inputs": {"images": ["decode", 0], "filename_prefix": "flashcloset"}},
        })
        return graph
