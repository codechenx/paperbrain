from pathlib import Path

from paperbrain.exporter import write_markdown


def export_markdown_files(output_dir: Path, pages: dict[str, str]) -> int:
    count = 0
    for relative_path, content in pages.items():
        write_markdown(output_dir / relative_path, content)
        count += 1
    return count

