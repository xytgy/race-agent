from pathlib import Path
from string import Template

_MODULE_DIR = Path(__file__).resolve().parent.parent


class PromptService:
    """Loads and renders prompt templates using string.Template ($-style substitution).

    Templates use $variable / ${variable} placeholders (NOT str.format's {}).
    This prevents user input containing {} from being misinterpreted as template
    directives — a prompt-injection / breakage vector with str.format().
    """

    def __init__(self, prompt_dir: str | None = None):
        self.prompt_dir = Path(prompt_dir) if prompt_dir else _MODULE_DIR / "prompts"

    def load(self, name: str) -> str:
        path = self.prompt_dir / name
        if not path.exists():
            raise FileNotFoundError(f"Prompt template '{name}' not found at {path}")
        return path.read_text(encoding="utf-8")

    def render(self, name: str, **kwargs) -> str:
        template = Template(self.load(name))
        try:
            return template.safe_substitute(**kwargs)
        except (KeyError, ValueError) as exc:
            raise ValueError(f"Template render failed: {exc}")

