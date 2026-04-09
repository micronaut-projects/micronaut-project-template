from argparse import ArgumentParser, Namespace
from pathlib import Path
from tempfile import TemporaryDirectory

START_MARKER = "<!-- BEGIN MICRONAUT GLOBAL CONTRIBUTING: Managed by micronaut-project-template/GLOBAL_CONTRIBUTING.md. Do not add or modify content below this marker in this file; your changes will be replaced by the sync workflow. -->"
END_MARKER = "<!-- END MICRONAUT GLOBAL CONTRIBUTING -->"
NEWLINE = chr(10)
REPO_ROOT = Path(__file__).resolve().parent.parent


def build_parser() -> ArgumentParser:
    parser = ArgumentParser()
    _ = parser.add_argument('--source-root', type=Path)
    _ = parser.add_argument('--target-root', type=Path)
    _ = parser.add_argument('--write', action='store_true')
    return parser


def sync_global_contributing(target_text: str, managed_block: str) -> str:
    if not managed_block.endswith(NEWLINE):
        managed_block += NEWLINE

    start_index = target_text.find(START_MARKER)

    if start_index != -1:
        updated = target_text[:start_index].rstrip() + NEWLINE + NEWLINE + managed_block
    else:
        prefix = target_text.rstrip()
        if prefix:
            updated = prefix + NEWLINE + NEWLINE + managed_block
        else:
            updated = managed_block

    if not updated.endswith(NEWLINE):
        updated += NEWLINE

    return updated


def managed_block_text(source_root: Path) -> str:
    return (source_root / 'GLOBAL_CONTRIBUTING.md').read_text()


def sync_file(source_root: Path, target_root: Path) -> None:
    target_file = target_root / 'CONTRIBUTING.md'
    lock_file = target_root / 'CONTRIBUTING.md.lock'
    if lock_file.exists():
        return

    managed_block = managed_block_text(source_root)
    target_text = target_file.read_text() if target_file.exists() else ''
    updated = sync_global_contributing(target_text, managed_block)
    _ = target_file.write_text(updated)


def test_append_when_marker_is_absent() -> None:
    managed_block = managed_block_text(REPO_ROOT)
    original = '# Local repo guide\n\nRepo-specific instructions.\n'

    updated = sync_global_contributing(original, managed_block)

    assert updated.startswith('# Local repo guide\n\nRepo-specific instructions.\n\n')
    assert START_MARKER in updated
    assert END_MARKER in updated
    assert updated.count(START_MARKER) == 1
    assert updated.rstrip().endswith(managed_block.rstrip())


# Existing start marker should replace the managed section and anything after it.
def test_replace_existing_managed_block() -> None:
    managed_block = managed_block_text(REPO_ROOT)
    original = (
        '# Local repo guide\n\nKeep this above.\n\n'
        + START_MARKER
        + '\nOld managed text that should disappear.\n'
        + END_MARKER
        + '\n'
        + 'Trailing local content that should also disappear.\n'
    )

    updated = sync_global_contributing(original, managed_block)

    assert updated.startswith('# Local repo guide\n\nKeep this above.\n\n')
    assert 'Old managed text that should disappear.' not in updated
    assert 'Trailing local content that should also disappear.' not in updated
    assert updated.count(START_MARKER) == 1
    assert updated.count(END_MARKER) == 1
    assert updated.rstrip().endswith(managed_block.rstrip())


# A broken block without the end marker should still be replaced without duplication.
def test_no_duplicate_block_when_end_marker_is_missing() -> None:
    managed_block = managed_block_text(REPO_ROOT)
    original = (
        '# Local repo guide\n\nKeep this above.\n\n'
        + START_MARKER
        + '\nBroken managed text without an end marker.\n'
    )

    updated = sync_global_contributing(original, managed_block)

    assert 'Broken managed text without an end marker.' not in updated
    assert updated.count(START_MARKER) == 1
    assert updated.count(END_MARKER) == 1
    assert updated.rstrip().endswith(managed_block.rstrip())


def test_lock_file_skips_sync(tmp_path: Path) -> None:
    source_root = REPO_ROOT
    target_root = tmp_path
    target_file = target_root / 'CONTRIBUTING.md'
    lock_file = target_root / 'CONTRIBUTING.md.lock'

    _ = target_file.write_text('# Local repo guide\n')
    _ = lock_file.write_text('locked\n')

    sync_file(source_root, target_root)

    assert target_file.read_text() == '# Local repo guide\n'


def run_tests() -> None:
    test_append_when_marker_is_absent()
    test_replace_existing_managed_block()
    test_no_duplicate_block_when_end_marker_is_missing()

    with TemporaryDirectory() as tmp_dir:
        test_lock_file_skips_sync(Path(tmp_dir))


def main() -> None:
    parser = build_parser()
    args: Namespace = parser.parse_args()
    source_root = getattr(args, 'source_root', None)
    target_root = getattr(args, 'target_root', None)
    write = bool(getattr(args, 'write', False))

    if write:
        if not isinstance(source_root, Path) or not isinstance(target_root, Path):
            raise SystemExit('--write requires --source-root and --target-root')
        sync_file(source_root.resolve(), target_root.resolve())
        return

    run_tests()
    print('Global CONTRIBUTING sync tests passed.')


if __name__ == '__main__':
    main()
