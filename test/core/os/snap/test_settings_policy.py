"""Runtime metadata selection preserves wrappers and delegate object identities."""

import pytest

from pylizlib.core.os.snap.copy_strategy import CopyMetadataMode, ExtendedMetadataCopyStrategy, SequentialFileCopyStrategy, VerifiedFileCopyStrategy
from pylizlib.core.os.snap.domain import SnapshotSettings


def test_runtime_selection_avoids_double_wrapping_and_preserves_explicit_wrappers():
    """Mode transitions differ from assigning an explicit wrapper while already BASIC."""
    first = SequentialFileCopyStrategy()
    second = VerifiedFileCopyStrategy()
    settings = SnapshotSettings(copy_strategy=first)
    settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
    wrapper = settings.copy_strategy
    assert wrapper.delegate is first
    settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
    assert settings.copy_strategy is wrapper
    settings.copy_strategy = second
    assert settings.copy_strategy.delegate is second
    settings.copy_metadata_mode = CopyMetadataMode.BASIC
    assert settings.copy_strategy is second

    explicit = ExtendedMetadataCopyStrategy(first)
    settings.copy_strategy = explicit
    settings.copy_metadata_mode = CopyMetadataMode.BASIC
    assert settings.copy_strategy is explicit
    settings.copy_metadata_mode = CopyMetadataMode.EXTENDED
    assert settings.copy_strategy is explicit
    settings.copy_metadata_mode = CopyMetadataMode.BASIC
    assert settings.copy_strategy is first
    with pytest.raises(TypeError, match="must be a CopyMetadataMode"):
        settings.copy_metadata_mode = "extended"
    assert settings.copy_metadata_mode is CopyMetadataMode.BASIC
    assert settings.copy_strategy is first
