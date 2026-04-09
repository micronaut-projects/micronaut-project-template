from pathlib import Path

START_MARKER = "<!-- BEGIN MICRONAUT GLOBAL CONTRIBUTING: Managed by micronaut-project-template/GLOBAL_CONTRIBUTING.md. Do not add or modify content below this marker in this file; your changes will be replaced by the sync workflow. -->"
END_MARKER = "<!-- END MICRONAUT GLOBAL CONTRIBUTING -->"
NEWLINE = chr(10)


def sync_global_contributing(target_text: str, managed_block: str) -> str:
    if not managed_block.endswith(NEWLINE):
        managed_block += NEWLINE

    start_index = target_text.find(START_MARKER)
    end_index = target_text.find(END_MARKER)

    if start_index != -1 and end_index != -1 and end_index >= start_index:
        end_index += len(END_MARKER)
        if end_index < len(target_text) and target_text[end_index:end_index + 1] == NEWLINE:
            end_index += 1
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


def test_append_when_marker_is_absent() -> None:
    managed_block = Path('GLOBAL_CONTRIBUTING.md').read_text()
    original = '# Local repo guide\n\nRepo-specific instructions.\n'

    updated = sync_global_contributing(original, managed_block)

    assert updated.startswith('# Local repo guide\n\nRepo-specific instructions.\n\n')
    assert START_MARKER in updated
    assert END_MARKER in updated
    assert updated.count(START_MARKER) == 1
    assert updated.rstrip().endswith(managed_block.rstrip())


def test_replace_existing_managed_block() -> None:
    managed_block = Path('GLOBAL_CONTRIBUTING.md').read_text()
    original = (
        '# Local repo guide\n\nKeep this above.\n\n'
        + START_MARKER
        + '\nOld managed text that should disappear.\n'
        + END_MARKER
        + '\n'
    )

    updated = sync_global_contributing(original, managed_block)

    assert updated.startswith('# Local repo guide\n\nKeep this above.\n\n')
    assert 'Old managed text that should disappear.' not in updated
    assert updated.count(START_MARKER) == 1
    assert updated.count(END_MARKER) == 1
    assert updated.rstrip().endswith(managed_block.rstrip())


if __name__ == '__main__':
    test_append_when_marker_is_absent()
    test_replace_existing_managed_block()
    print('Global CONTRIBUTING sync tests passed.')
