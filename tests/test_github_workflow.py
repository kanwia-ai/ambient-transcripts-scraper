# tests/test_github_workflow.py
import yaml
from pathlib import Path

def test_github_workflow_exists():
    workflow_path = Path(".github/workflows/scrape.yml")
    assert workflow_path.exists()

    with open(workflow_path) as f:
        workflow = yaml.safe_load(f)

    # YAML parses 'on' key as boolean True
    assert True in workflow
    assert 'schedule' in workflow[True]
    assert 'workflow_dispatch' in workflow[True]