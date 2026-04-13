import subprocess
import sys


def test_module_entrypoint_shows_help() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "paperbrain.main", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "PaperBrain CLI" in proc.stdout
    assert "setup" in proc.stdout
