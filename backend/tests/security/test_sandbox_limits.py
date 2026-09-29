import sys
from services.repository_analysis.sandbox import ParserSandbox


def test_sandbox_does_not_set_process_wide_cpu_limit(monkeypatch):
    calls = []
    if "resource" in sys.modules or sys.platform != "win32":
        import resource
        monkeypatch.setattr(resource, "setrlimit", lambda res, lim: calls.append((res, lim)))
    else:
        # On Windows, mock resource module to test POSIX logic
        import types
        mock_resource = types.ModuleType("resource")
        mock_resource.RLIMIT_CPU = 0
        mock_resource.RLIMIT_AS = 9
        mock_resource.setrlimit = lambda res, lim: calls.append((res, lim))
        monkeypatch.setitem(sys.modules, "resource", mock_resource)
        monkeypatch.setattr(sys, "platform", "linux")

    sandbox = ParserSandbox()
    sandbox.apply_process_limits()

    # Verify RLIMIT_CPU was NOT set (to prevent server killing)
    for res, lim in calls:
        assert res != 0, "RLIMIT_CPU must not be applied to the shared server process"
