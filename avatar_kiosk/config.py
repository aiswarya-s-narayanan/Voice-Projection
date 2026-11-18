from dataclasses import dataclass
from pathlib import Path
import os
import sysconfig

ROOT = Path(__file__).resolve().parents[1]


def prepare_gpu_environment():
    """Expose pip-installed CUDA libraries to the newly spawned worker's loader."""
    site = Path(sysconfig.get_paths()["purelib"])
    libraries = [str(path) for path in sorted((site / "nvidia").glob("*/lib"))]
    existing = os.environ.get("LD_LIBRARY_PATH", "").split(":")
    os.environ["LD_LIBRARY_PATH"] = ":".join(dict.fromkeys(p for p in libraries + existing if p))


@dataclass(frozen=True)
class Settings:
    ditto: str = str(ROOT / "vendor/ditto")
    image: str = str(ROOT / "Avatar/avatar.jpg")
    data_root: str = str(ROOT / "models/ditto/ditto_pytorch")
    config: str = str(ROOT / "models/ditto/ditto_cfg/v0.4_hubert_cfg_pytorch.pkl")
    max_size: int = 1280
    batch_size: int = 1
    render_stride: int = 3
    sampling_steps: int = 10

    @classmethod
    def from_env(cls):
        defaults = cls()
        return cls(
            ditto=os.environ.get("DITTO_REPO", defaults.ditto),
            image=os.environ.get("AVATAR_IMAGE", defaults.image),
            data_root=os.environ.get("DITTO_DATA_ROOT", defaults.data_root),
            config=os.environ.get("DITTO_CONFIG", defaults.config),
            max_size=int(os.environ.get("AVATAR_MAX_SIZE", "1280")),
            batch_size=int(os.environ.get("AVATAR_BATCH_SIZE", "1")),
            render_stride=max(1, min(5, int(os.environ.get("AVATAR_RENDER_STRIDE", "3")))),
            sampling_steps=int(os.environ.get("AVATAR_SAMPLING_STEPS", "10")),
        )

    def missing(self):
        return [p for p in (self.image, self.config, self.data_root,
                            str(Path(self.ditto) / "stream_pipeline_online.py")) if not Path(p).exists()]
