"""Download only official PyTorch Ditto assets, not every TensorRT variant."""
from pathlib import Path
from huggingface_hub import snapshot_download

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    snapshot_download(
        repo_id="digital-avatar/ditto-talkinghead",
        local_dir=root / "models/ditto",
        allow_patterns=["ditto_pytorch/**", "ditto_cfg/v0.4_hubert_cfg_pytorch.pkl", "README.md", "LICENSE*"],
    )
