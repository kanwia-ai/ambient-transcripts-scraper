# Baseline test to verify test framework is working
# This test should always pass

def test_baseline():
    """Verify pytest is working correctly."""
    assert True


def test_python_version():
    """Verify we're running Python 3.8+."""
    import sys
    assert sys.version_info >= (3, 8)
