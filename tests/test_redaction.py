from task_manager_cli.privacy.redactor import Redactor


def test_redacts_sensitive_patterns_and_private_records():
    redactor = Redactor()
    assert "[REDACTED]" in redactor.redact("token=abcdef1234567890").text
    private = redactor.redact("anything", private=True)
    assert private.redacted
    assert "private" in private.text
