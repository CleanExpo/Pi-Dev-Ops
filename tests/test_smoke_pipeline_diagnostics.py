from scripts.smoke_test_pipeline import PipelineAssertions


def test_smoke_retains_phase_and_error_events_for_failure_report():
    assertions = PipelineAssertions()

    phase_line = assertions.observe_event(
        {"type": "phase", "text": "[1/5] Cloning repository..."},
        elapsed_s=1.2,
    )
    error_line = assertions.observe_event(
        {"type": "error", "text": "Clone failed after 3 attempts"},
        elapsed_s=8.4,
    )

    assert phase_line == "  [t+1s] phase: [1/5] Cloning repository..."
    assert error_line == "  [t+8s] error: Clone failed after 3 attempts"
    assert assertions.diagnostics == [phase_line, error_line]
    assert "Clone failed after 3 attempts" in assertions.summary()
