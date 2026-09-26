from environments.mkoshp_2026.judge import perform

def perform_tests(runner, source_code=None):
    return perform('C', runner, source_code)
