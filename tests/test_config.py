"""Settings: the OpenFIGI key from data/settings.toml or the environment."""

import pytest

from thirteenf import config


@pytest.fixture()
def settings(tmp_path, monkeypatch):
    path = tmp_path / "settings.toml"
    monkeypatch.setattr(config, "SETTINGS_PATH", path)
    monkeypatch.delenv("OPENFIGI_API_KEY", raising=False)
    return path


def test_the_template_is_created_once_and_has_no_key(settings):
    assert config.ensure_settings_file() == settings
    assert 'openfigi_api_key = ""' in settings.read_text(encoding="utf-8")
    assert config.settings_file_value("openfigi_api_key") == ""
    settings.write_text('openfigi_api_key = "from-file"\n', encoding="utf-8")
    config.ensure_settings_file()  # does not overwrite
    assert config.settings_file_value("openfigi_api_key") == "from-file"


def test_the_key_comes_from_the_file(settings):
    settings.write_text('# comment\nopenfigi_api_key = "  abc-123  "\n', encoding="utf-8")
    assert config.openfigi_api_key() == "abc-123"


def test_an_environment_variable_overrides_the_file(settings, monkeypatch):
    settings.write_text('openfigi_api_key = "from-file"\n', encoding="utf-8")
    monkeypatch.setenv("OPENFIGI_API_KEY", "from-env")
    assert config.openfigi_api_key() == "from-env"


def test_a_key_pasted_without_quotes_still_reads(settings):
    settings.write_text("openfigi_api_key = 8637-abcd-ef01\n", encoding="utf-8")
    assert config.settings_file_value("openfigi_api_key") == "8637-abcd-ef01"


def test_a_missing_file_means_no_value(settings):
    assert config.settings_file_value("openfigi_api_key") == ""
