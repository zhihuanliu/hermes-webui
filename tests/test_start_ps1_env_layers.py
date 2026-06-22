from pathlib import Path


START_PS1 = Path("start.ps1").read_text(encoding="utf-8")


def test_start_ps1_loads_environment_specific_env_file():
    assert "[ValidateSet('development', 'production')]" in START_PS1
    assert "[string]$Environment = 'development'" in START_PS1
    assert '$environmentEnvFile = Join-Path $RepoRoot ".env.$Environment"' in START_PS1
    assert "Import-HermesEnvFile -Path $baseEnvFile" in START_PS1
    assert "Import-HermesEnvFile -Path $environmentEnvFile" in START_PS1


def test_start_ps1_preserves_explicit_process_environment():
    assert "$explicitEnvKeys.Contains($key)" in START_PS1
    assert START_PS1.index("Get-ChildItem Env:") < START_PS1.index(
        "Import-HermesEnvFile -Path $baseEnvFile"
    )
