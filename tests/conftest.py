import pytest
import logging
from unittest.mock import MagicMock, patch
from pathlib import Path
from src.core.context import PortingContext

@pytest.fixture
def mock_context():
    """Returns a mock PortingContext."""
    mock = MagicMock(spec=PortingContext)
    mock.is_eu_port = False  # Default to CN port
    mock.is_cn = False
    mock.logger = logging.getLogger("MockContext")
    return mock

@pytest.fixture
def mock_smali_func():
    """Returns a mock smali_patch function."""
    return MagicMock()

@pytest.fixture
def mock_xml():
    """
    Mocks src.modules.base.XmlUtils by replacing it with a MagicMock.
    When SettingsModule (or any BaseModule subclass) calls XmlUtils(), it will get this mock.
    """
    with patch("src.modules.base.XmlUtils") as MockClass:
        instance = MockClass.return_value
        # Default behavior:
        # get_res_dir(work_dir) -> work_dir / "res"
        instance.get_res_dir.side_effect = lambda wd: wd / "res"
        
        # get_id(res_dir, name) -> "0xmockid"
        instance.get_id.return_value = "0xmockid"
        
        yield instance

@pytest.fixture
def base_fixtures(mock_smali_func, mock_context, mock_xml):
    """Bundle common fixtures."""
    return {
        "smali": mock_smali_func,
        "ctx": mock_context,
        "xml": mock_xml
    }
