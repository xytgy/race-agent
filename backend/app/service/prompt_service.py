from pathlib import Path

_MODULE_DIR = Path(__file__).resolve().parent.parent


class PromptService:
    def __init__(self, prompt_dir: str | None = None):
        self.prompt_dir = Path(prompt_dir) if prompt_dir else _MODULE_DIR / "prompts"

    def load(self, name: str) -> str:
        path = self.prompt_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Prompt template '{name}' not found at {path}")
        return path.read_text(encoding="utf-8")

    def render(self, name: str, **kwargs) -> str:
        template = self.load(name)
        try:
            return template.format(**kwargs)
        except (KeyError, IndexError, ValueError) as exc:
            raise ValueError(f"Template render failed: {exc}")

