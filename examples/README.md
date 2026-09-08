# First-release examples

The first real-model walkthrough is [LiveCC](../docs/livecc-adapter.md).
Use [logical.json](livecc/logical.json) for the README's quick QA/Proactive
execution check, or [wall_clock.json](livecc/wall_clock.json) with matching Core
pacing for timing experiments. Obtain the upstream source, weights and runtime
separately; OSB contains no model weights.

The [test double](../src/open_stream_bench/adapters.py) and
[synthetic fixture generator](../scripts/make_smoke_fixture.py) exercise the
complete software pipeline without a model. The test double reads GT on purpose
and must only be used with `--synthetic`; its scores are never benchmark results.

ThinkStream launch examples are deferred until fresh validation of its corrected
flush behavior. Its Python adapter import remains for existing users, with CPU
contract tests, but is not a validated public walkthrough. AURA, JoyAI, MOSS,
VideoLLM-online and MiniCPM deployments are not shipped as release examples.
They can still be installed externally through `module:Class`; their presence
elsewhere is not a certification of their OSB protocol conformance.

Even for the retained example, successful execution is distinct from official
result eligibility. Inspect response behavior, failures, judge coverage and
telemetry; Native status requires implementation review beyond declarations.
