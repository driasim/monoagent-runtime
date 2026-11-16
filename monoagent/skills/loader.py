"""Reusable operational skill and playbook loader."""

import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PlaybookStep(BaseModel):
    step_id: str
    description: str
    expected_tool: Optional[str] = None
    fallback_strategy: Optional[str] = None


class ReusablePlaybook(BaseModel):
    name: str
    version: str
    description: str
    author: str
    triggers: List[str] = Field(default_factory=list)
    required_permissions: List[str] = Field(default_factory=list)
    steps: List[PlaybookStep] = Field(default_factory=list)


class PlaybookRegistry:
    """Manages versioned, reusable skills and operational playbooks."""

    def __init__(self):
        self.playbooks: Dict[str, ReusablePlaybook] = {}

    def load_from_yaml(self, yaml_content: str) -> ReusablePlaybook:
        data = yaml.safe_load(yaml_content)
        playbook = ReusablePlaybook(**data)
        self.playbooks[playbook.name] = playbook
        return playbook

    def load_from_file(self, file_path: str) -> ReusablePlaybook:
        path = Path(file_path)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        return self.load_from_yaml(content)

    def get_playbook(self, name: str) -> Optional[ReusablePlaybook]:
        return self.playbooks.get(name)

    def find_playbook_for_intent(self, intent: str) -> Optional[ReusablePlaybook]:
        intent_lower = intent.lower()
        for pb in self.playbooks.values():
            for trigger in pb.triggers:
                if trigger.lower() in intent_lower:
                    return pb
        return None
