from trace_bench.scoring import (
    JudgeRouter,
    judge_from_settings,
    assess_official_eligibility,
    assemble_response_episodes,
    extract_choice,
    extract_recoverable_choice,
    prediction_from_query_events,
    score_proactive,
    score_qa,
    score_records,
    summarize_telemetry,
)


def test_qa_prediction_assembles_streaming_deltas_instead_of_last_fragment():
    events = [
        {
            "record_id": "qa-delta",
            "kind": "answer",
            "logical_time_s": 1.0,
            "text": "A",
            "response_id": "qa-response",
            "sequence_id": 0,
            "text_mode": "delta",
            "telemetry": {"query_dispatch_perf_ns": 100},
        },
        {
            "record_id": "qa-delta",
            "kind": "answer",
            "logical_time_s": 1.0,
            "text": ".",
            "response_id": "qa-response",
            "sequence_id": 1,
            "text_mode": "delta",
            "is_final": True,
            "telemetry": {"query_dispatch_perf_ns": 100},
        },
    ]
    assert prediction_from_query_events(events) == "A."
    result = score_qa(
        [{"record_id": "qa-delta", "answer": "A", "prediction": "."}],
        events=events,
    )
    assert result["accuracy"] == 1.0
    assert result["scored_records"][0]["prediction"] == "A."
    assert result["scored_records"][0]["prediction_stored"] == "."


def test_response_assembly_excludes_suppressed_prefill_and_shutdown_drain():
    events = [
        {
            "kind": "answer",
            "logical_time_s": 1.0,
            "text": "prefill",
            "response_id": "prefill",
            "telemetry": {"provider_output_suppressed": True},
        },
        {
            "kind": "answer",
            "logical_time_s": 2.0,
            "text": "eligible",
            "response_id": "eligible",
            "telemetry": {},
        },
        {
            "kind": "answer",
            "logical_time_s": 8.0,
            "text": "drain",
            "response_id": "drain",
            "telemetry": {"eligible_for_scoring": False, "suppression_reason": "shutdown_drain"},
        },
    ]
    episodes = assemble_response_episodes(events)
    assert [episode["text"] for episode in episodes] == ["eligible"]


def test_choice_normalization_preserves_raw_contract():
    assert extract_choice("<think>reason</think>\nThe answer is B") is None
    result = score_qa([{"record_id": "1", "answer": "B", "prediction": "B"}])
    assert result["accuracy"] == 1.0
    assert result["scored_records"][0]["prediction"] == "B"


def test_choice_normalization_rejects_ambiguity_and_uses_actual_option_labels():
    assert extract_choice("A or B", {"A", "B"}) is None
    result = score_qa(
        [
            {
                "record_id": "five-options",
                "answer": "E",
                "options": ["A. one", "B. two", "C. three", "D. four", "E. five"],
                "prediction": "E",
            }
        ]
    )
    assert result["accuracy"] == 1.0


def test_paper_profile_recovers_explicit_choice_without_changing_strict_parser():
    assert extract_recoverable_choice("The answer is C.", {"A", "B", "C"}) == "C"
    assert extract_recoverable_choice("C. option text", {"A", "B", "C"}) == "C"
    assert extract_recoverable_choice("C. A person walks.", {"A", "B", "C"}) == "C"
    assert extract_recoverable_choice("A or B", {"A", "B", "C"}) is None
    records = [
        {
            "record_id": "paper-qa",
            "answer": "C",
            "options": ["A. one", "B. two", "C. three"],
            "prediction": "The answer is C.",
        }
    ]
    legacy = score_records("qa", records)
    paper = score_records("qa", records, scoring_profile="paper-v1")
    assert legacy["accuracy"] == 0.0
    assert paper["accuracy"] == 1.0
    assert paper["strict_accuracy"] == 0.0
    assert paper["scoring_profile"] == "paper-v1"


def test_paper_proactive_profile_reports_global_false_alarm_and_window_miss():
    records = [
        {
            "record_id": "paper-proactive",
            "task": "proactive",
            "task_type": "exact",
            "instruction": "Say it",
            "windows": [
                {"start_s": 2.0, "end_s": 4.0, "expected_answer": "yes"},
                {"start_s": 6.0, "end_s": 8.0, "expected_answer": "yes"},
            ],
        }
    ]
    events = [
        {
            "record_id": "paper-proactive",
            "kind": "answer",
            "logical_time_s": 0.5,
            "text": "WAIT",
            "response_id": "wait",
            "is_final": True,
        },
        {
            "record_id": "paper-proactive",
            "kind": "answer",
            "logical_time_s": 1.0,
            "text": "too early",
            "response_id": "early",
            "is_final": True,
        },
        {
            "record_id": "paper-proactive",
            "kind": "answer",
            "logical_time_s": 2.5,
            "text": "yes",
            "response_id": "first",
            "is_final": True,
        },
        {
            "record_id": "paper-proactive",
            "kind": "answer",
            "logical_time_s": 12.0,
            "text": "late",
            "response_id": "late",
            "is_final": True,
        },
    ]
    result = score_records(
        "proactive", records, events=events, scoring_profile="paper-v1"
    )
    assert result["false_alarm_response_episode_count"] == 1
    assert result["false_alarm_denominator_episode_count"] == 3
    assert result["false_alarm_rate"] == 1 / 3
    assert result["missed_window_count"] == 1
    assert result["miss_rate"] == 0.5


def test_telemetry_summary_never_estimates_missing_values():
    events = [
        {
            "record_id": "1",
            "kind": "observation",
            "telemetry": {"arrival_perf_ns": 10, "commit_perf_ns": None},
        },
        {
            "record_id": "1",
            "kind": "telemetry",
            "telemetry": {
                "query_dispatch_perf_ns": 50,
                "response_completion_perf_ns": 60,
            },
        },
        {
            "record_id": "1",
            "kind": "answer",
            "telemetry": {
                "query_dispatch_perf_ns": 100,
                "first_token_perf_ns": 1_000_100,
                "response_completion_perf_ns": 2_000_100,
                "model_calls": [
                    {
                        "stage": "main",
                        "start_perf_ns": 200,
                        "end_perf_ns": 1_000_200,
                        "submitted_frame_occurrences": 4,
                        "submitted_pixels": 400,
                        "input_text_tokens": 8,
                        "output_tokens": 2,
                        "num_cached_tokens": 3,
                    }
                ],
            },
        },
    ]
    result = summarize_telemetry(events, [{"record_id": "1", "status": "completed"}])
    assert result["responsiveness"]["ttft_ms"]["observed_count"] == 1
    assert result["responsiveness"]["stream_completion_rate"]["value"] == 0.0
    assert result["visual_workload"]["submitted_frame_occurrences"] == 4
    assert result["visual_workload"]["duplicate_frame_occurrences"] == 4
    assert result["text_and_inference"]["input_text_tokens"] == 8
    assert result["text_and_inference"]["prefix_cached_tokens"] == 3
    assert result["telemetry_coverage"]["query_ttft"] == 1.0
    assert result["gpu_memory"]["telemetry_available"] is False


def test_proactive_latency_uses_answered_window_population_not_all_episodes():
    events = [
        {
            "record_id": "proactive",
            "kind": "answer",
            "logical_time_s": 1.0,
            "text": "first",
            "response_id": "response-1",
            "is_final": True,
            "telemetry": {"proactive_response_latency_ms": 12.0},
        },
        {
            "record_id": "proactive",
            "kind": "answer",
            "logical_time_s": 2.0,
            "text": "redundant",
            "response_id": "response-2",
            "is_final": True,
            "telemetry": {},
        },
    ]
    records = [
        {
            "record_id": "proactive",
            "task": "proactive",
            "status": "completed",
            "per_window_results": [
                {"source": "in_window", "is_answered": True, "latency_ms": 12.0},
                {"source": "in_window", "is_answered": True, "latency_ms": None},
                {"source": "before_window", "is_answered": True, "latency_ms": None},
            ],
        }
    ]

    result = summarize_telemetry(events, records)

    latency = result["responsiveness"]["proactive_response_latency_ms"]
    assert latency["population"] == "strict_in_window_answer_windows"
    assert latency["population_count"] == 2
    assert latency["observed_count"] == 1
    assert latency["coverage"] == 0.5
    assert result["telemetry_coverage"]["proactive_response_latency"] == 0.5


def test_qa_history_processing_is_reported_separately_from_query_work():
    events = [
        {
            "record_id": "qa-history",
            "kind": "observation",
            "logical_time_s": 0.0,
            "telemetry": {
                "arrival_perf_ns": 100,
                "commit_perf_ns": 200,
                "frame_processing_ms": 0.0001,
            },
        },
        {
            "record_id": "qa-history",
            "kind": "answer",
            "logical_time_s": 1.0,
            "text": "A",
            "telemetry": {
                "query_dispatch_perf_ns": 1_000,
                "first_token_perf_ns": 1_100,
                "model_calls": [
                    {
                        "stage": "history",
                        "start_perf_ns": 300,
                        "end_perf_ns": 900,
                        "submitted_frame_occurrences": 1,
                        "submitted_pixels": 16,
                        "input_text_tokens": 2,
                        "output_tokens": 1,
                    },
                    {
                        "stage": "qa_query",
                        "start_perf_ns": 1_010,
                        "end_perf_ns": 1_200,
                        "input_text_tokens": 8,
                        "output_tokens": 1,
                    },
                ],
            },
        },
    ]
    result = summarize_telemetry(
        events,
        [{"record_id": "qa-history", "task": "qa", "status": "completed"}],
    )
    history = result["qa_history_processing"]
    assert history["model_call_count"] == 1
    assert history["submitted_frame_occurrences"] == 1
    assert history["input_text_tokens"] == 2
    assert result["text_and_inference"]["model_call_count"] == 2


def test_proactive_windows_are_half_open():
    result = score_proactive(
        [
            {
                "record_id": "boundary",
                "windows": [
                    {"start_s": 1.0, "end_s": 2.0, "expected_answer": "first"},
                    {"start_s": 2.0, "end_s": 3.0, "expected_answer": "second"},
                ],
                "events": [
                    {"kind": "answer", "logical_time_s": 2.0, "text": "second"},
                ],
            }
        ],
        window_boundary="half_open",
    )
    assert result["correct_windows"] == 1
    assert result["scored_records"][0]["per_window_results"][0]["source"] == "no_output"
    assert result["scored_records"][0]["per_window_results"][1]["source"] == "in_window"


def test_proactive_fixed_window_and_eventual_view_ignore_legacy_deadline():
    result = score_proactive(
        [
            {
                "record_id": "fixed-and-eventual",
                "deadline_s": 2.0,
                "video_duration_s": 12.0,
                "metadata": {
                    "trigger_annotations": [
                        {
                            "trigger_type": "event_completion",
                            "point_trigger_s": 1.0,
                            "response_window_start_s": 1.0,
                            "response_window_end_s": 6.0,
                            "answer": "first",
                        },
                        {
                            "trigger_type": "event_completion",
                            "point_trigger_s": 10.0,
                            "response_window_start_s": 10.0,
                            "response_window_end_s": 15.0,
                            "answer": "second",
                        },
                    ]
                },
                "windows": [
                    {"start_s": 1.0, "end_s": 6.0, "expected_answer": "first"},
                    {"start_s": 10.0, "end_s": 15.0, "expected_answer": "second"},
                ],
                "events": [
                    {"kind": "observation", "logical_time_s": 1.0, "telemetry": {}},
                    {"kind": "answer", "logical_time_s": 8.0, "text": "first"},
                ],
            }
        ],
        proactive_window_s=5.0,
    )
    strict = result["strict_all_window"]
    eventual = result["post_trigger_eventual"]
    windows = result["scored_records"][0]["per_window_results"]
    events = result["scored_records"][0]["per_eventual_results"]
    assert windows[0]["end_s"] == 6.0
    assert windows[0]["source"] == "no_output"
    assert windows[1]["source"] == "before_window"
    assert strict["window_accuracy"] == 0.0
    assert events[0]["end_s"] == 10.0
    assert events[0]["source"] == "eventual"
    assert eventual["eventual_accuracy"] == 0.5


def test_dense_windows_are_reported_without_overlap_or_semantic_reassignment():
    result = score_proactive(
        [
            {
                "record_id": "dense",
                "video_duration_s": 3.0,
                "windows": [
                    {"start_s": 1.0, "end_s": 1.1, "expected_answer": "first"},
                    {"start_s": 2.0, "end_s": 2.1, "expected_answer": "second"},
                ],
                "events": [
                    {"kind": "observation", "logical_time_s": 1.0, "telemetry": {}},
                    {"kind": "observation", "logical_time_s": 2.0, "telemetry": {}},
                    {"kind": "answer", "logical_time_s": 2.0, "text": "second"},
                ],
            }
        ],
        proactive_window_s=5.0,
    )
    windows = result["scored_records"][0]["per_window_results"]
    assert windows[0]["end_s"] == 2.0
    assert windows[0]["inter_trigger_gap_s"] == 1.0
    assert windows[0]["effective_window_duration_s"] == 1.0
    assert windows[0]["crowded_window"] is True
    assert windows[0]["observed_frame_count"] == 1
    assert windows[1]["source"] == "in_window"
    assert result["crowded_window_count"] == 1
    assert result["non_crowded_window_count"] == 1


def test_final_eventual_view_never_ends_before_final_strict_window():
    result = score_proactive(
        [
            {
                "record_id": "final-grace",
                "video_duration_s": 2.0,
                "windows": [
                    {"start_s": 1.0, "end_s": 1.1, "expected_answer": "event"}
                ],
                "events": [
                    {"kind": "answer", "logical_time_s": 4.0, "text": "event"}
                ],
            }
        ],
        proactive_window_s=5.0,
    )
    assert result["scored_records"][0]["per_eventual_results"][0]["end_s"] == 6.0
    assert result["post_trigger_eventual"]["eventual_accuracy"] == 1.0


def test_final_eventual_view_does_not_extend_to_source_video_tail():
    result = score_proactive(
        [
            {
                "record_id": "ovo_bench_proactive:1469",
                "deadline_s": 347.0,
                "video_duration_s": 7064.182,
                "windows": [
                    {
                        "start_s": 317.0,
                        "end_s": 322.0,
                        "expected_answer": "walks past him",
                    }
                ],
                "events": [
                    {
                        "kind": "answer",
                        "logical_time_s": 323.0,
                        "text": "walks past him",
                    }
                ],
            }
        ],
        proactive_window_s=5.0,
    )
    assert result["scored_records"][0]["per_eventual_results"][0]["end_s"] == 322.0
    assert result["post_trigger_eventual"]["eventual_accuracy"] == 0.0


def test_state_interval_eventual_view_ends_at_state_end():
    result = score_proactive(
        [
            {
                "record_id": "state",
                "video_duration_s": 100.0,
                "metadata": {
                    "trigger_annotations": [
                        {
                            "trigger_type": "state_interval",
                            "response_policy": "reviewed_state_interval",
                            "response_window_start_s": 2.0,
                            "response_window_end_s": 4.0,
                            "interval_start_s": 2.0,
                            "interval_end_s": 4.0,
                            "answer": "state",
                        }
                    ]
                },
                "windows": [{"start_s": 2.0, "end_s": 4.0, "expected_answer": "state"}],
                "events": [{"kind": "answer", "logical_time_s": 4.0, "text": "state"}],
            }
        ],
        proactive_window_s=10.0,
    )
    assert result["post_trigger_eventual"]["eventual_accuracy"] == 0.0
    assert result["scored_records"][0]["per_eventual_results"][0]["source"] == "no_output"


def test_default_proactive_boundary_is_half_open():
    result = score_proactive(
        [
            {
                "record_id": "boundary-inclusive",
                "windows": [{"start_s": 1.0, "end_s": 2.0, "expected_answer": "answer"}],
                # The default point tolerance is W=5s, so the half-open
                # boundary is t=6.0 rather than the legacy raw end field.
                "events": [{"kind": "answer", "logical_time_s": 6.0, "text": "answer"}],
            }
        ]
    )
    window = result["scored_records"][0]["per_window_results"][0]
    assert window["source"] == "no_output"
    assert window["score"] == 0.0


def test_response_episode_assembly_groups_deltas_and_closes_on_wait():
    episodes = assemble_response_episodes(
        [
            {
                "kind": "answer",
                "logical_time_s": 2.0,
                "text": "walks",
                "response_id": "r1",
                "sequence_id": 2,
                "text_mode": "delta",
                "is_final": True,
            },
            {
                "kind": "answer",
                "logical_time_s": 1.0,
                "text": "She",
                "response_id": "r1",
                "sequence_id": 1,
                "text_mode": "delta",
            },
            {"kind": "wait", "logical_time_s": 3.0, "text": "WAIT"},
        ]
    )
    assert len(episodes) == 1
    assert episodes[0]["text"] == "She walks"
    assert episodes[0]["source_event_indices"] == [1, 0]


def test_response_episode_assembly_accepts_legacy_telemetry_fields():
    episodes = assemble_response_episodes(
        [
            {
                "kind": "answer",
                "logical_time_s": 1.0,
                "text": "A",
                "telemetry": {"response_id": "r", "text_mode": "delta"},
            },
            {
                "kind": "answer",
                "logical_time_s": 2.0,
                "text": "B",
                "telemetry": {
                    "response_id": "r",
                    "text_mode": "delta",
                    "is_final": True,
                },
            },
        ]
    )
    assert [episode["text"] for episode in episodes] == ["A B"]


def test_vlm_router_persists_score_and_raw_response():
    def transport(_request, _timeout):
        return b'{"choices":[{"message":{"content":"0.75"}}]}'

    judge = JudgeRouter(
        mode="vlm",
        base_url="http://judge/v1",
        model="test-judge",
        transport=transport,
    )
    result = score_proactive(
        [
            {
                "record_id": "semantic",
                "task_type": "SSR",
                "instruction": "What happens?",
                "windows": [{"start_s": 1.0, "end_s": 2.0, "expected_answer": "walks"}],
                "events": [{"kind": "answer", "logical_time_s": 1.0, "text": "walking"}],
            }
        ],
        judge=judge,
    )
    window = result["scored_records"][0]["per_window_results"][0]
    assert window["score"] == 0.75
    assert window["judge"]["method"] == "vlm"
    assert window["judge"]["raw_response"] == "0.75"
    assert result["judge"]["method_counts"] == {"vlm": 1}
    assert result["judge"]["method_counts_by_view"] == {
        "strict": {"vlm": 1},
        "eventual": {"vlm": 1},
    }


def test_proactive_strips_standalone_answer_delimiter_only_for_matching():
    result = score_proactive(
        [
            {
                "record_id": "delimiter",
                "windows": [
                    {"start_s": 0.0, "end_s": 2.0, "expected_answer": "1"},
                    {"start_s": 4.0, "end_s": 6.0, "expected_answer": "2"},
                ],
                "events": [
                    {"kind": "answer", "logical_time_s": 1.0, "text": ": 1"},
                    {"kind": "answer", "logical_time_s": 3.0, "text": ": 2"},
                    {"kind": "answer", "logical_time_s": 10.0, "text": "intrusion"},
                ],
            }
        ]
    )
    windows = result["scored_records"][0]["per_window_results"]
    assert windows[0]["score"] == 1
    assert windows[0]["prediction"] == ": 1"
    assert windows[1]["source"] == "before_window"
    assert result["outside_window_intrusion_count"] == 1


def test_workload_keys_observations_by_record_and_frame_id():
    events = [
        {
            "record_id": "record-a",
            "kind": "answer",
            "telemetry": {
                "frame_telemetry": [{"observation_id": "frame-0", "submitted_occurrences": 1}],
                "model_calls": [],
            },
        },
        {
            "record_id": "record-b",
            "kind": "answer",
            "telemetry": {
                "frame_telemetry": [{"observation_id": "frame-0", "submitted_occurrences": 1}],
                "model_calls": [],
            },
        },
    ]
    result = summarize_telemetry(
        events,
        [
            {"record_id": "record-a", "status": "completed"},
            {"record_id": "record-b", "status": "completed"},
        ],
    )
    workload = result["visual_workload"]
    assert workload["unique_submitted_frames"] == 2
    assert workload["dropped_frames"] == 0


def test_zero_occurrence_history_rows_are_not_submitted_workload():
    events = [
        {
            "record_id": "record-a",
            "kind": "telemetry",
            "telemetry": {
                "frame_telemetry": [
                    {"observation_id": "frame-0", "submitted_occurrences": 0}
                ],
                "model_calls": [],
            },
        }
    ]
    result = summarize_telemetry(
        events,
        [{"record_id": "record-a", "status": "completed"}],
    )
    workload = result["visual_workload"]
    assert workload["unique_submitted_frames"] == 0
    assert workload["dropped_frames"] == 0


def test_dropped_rate_uses_unique_submissions_not_commits():
    events = [
        {
            "record_id": "r",
            "kind": "observation",
            "telemetry": {"observation_id": "f0", "commit_perf_ns": 10},
        },
        {
            "record_id": "r",
            "kind": "observation",
            "telemetry": {"observation_id": "f1", "commit_perf_ns": 11},
        },
        {
            "record_id": "r",
            "kind": "telemetry",
            "telemetry": {
                "frame_telemetry": [
                    {"observation_id": "f0", "submitted_occurrences": 1}
                ]
            },
        },
    ]
    result = summarize_telemetry(events, [{"record_id": "r", "status": "completed"}])
    assert result["responsiveness"]["dropped_frame_rate"]["numerator"] == 1
    assert result["responsiveness"]["dropped_frame_rate"]["value"] == 0.5


def test_gpu_attribution_requires_every_resource_sample():
    events = [
        {
            "record_id": "r",
            "kind": "telemetry",
            "telemetry": {
                "gpu": {
                    "attribution_ok": True,
                    "devices": [{"device_id": 0, "peak_bytes": 10}],
                }
            },
        },
        {
            "record_id": "r",
            "kind": "telemetry",
            "telemetry": {
                "gpu": {
                    "attribution_ok": False,
                    "devices": [{"device_id": 0, "peak_bytes": 20}],
                }
            },
        },
    ]
    result = summarize_telemetry(events, [{"record_id": "r", "status": "completed"}])
    assert result["gpu_memory"]["attribution_ok"] is False


def test_proactive_sidecar_events_are_authoritative():
    records = [
        {
            "record_id": "p",
            "windows": [{"start_s": 1.0, "expected_answer": "right"}],
            "events": [{"kind": "answer", "logical_time_s": 1.0, "text": "right"}],
        }
    ]
    sidecar = [
        {"record_id": "p", "kind": "answer", "logical_time_s": 1.0, "text": "wrong"}
    ]
    result = score_proactive(records, events=sidecar)
    assert result["strict_all_window"]["window_accuracy"] == 0.0


def test_official_eligibility_reports_missing_telemetry_and_judge_errors():
    metrics = {
        "execution_track": {
            "visual_state": "Native Streaming",
            "proactive_primary_eligible": True,
        },
        "telemetry": {
            "telemetry_coverage": {},
            "gpu_memory": {"attribution_ok": False},
        },
        "judge": {"error_counts": {"vlm_unavailable": 1}},
    }
    result = assess_official_eligibility(
        "proactive", metrics, synthetic=False, provisional=False
    )
    assert result["official_eligible"] is False
    assert "judge_incomplete" in result["reasons"]
    assert "incomplete_telemetry:gpu_memory_attribution" in result["reasons"]


def test_proactive_score_reports_missing_trigger_metadata():
    result = score_proactive(
        [
            {
                "record_id": "legacy",
                "windows": [{"start_s": 1.0, "end_s": 2.0, "expected_answer": "answer"}],
                "events": [],
            }
        ]
    )
    assert result["trigger_metadata"]["complete"] is False


def test_streaming_deltas_count_as_one_query_for_ttft_coverage():
    events = [
        {
            "record_id": "qa",
            "kind": "answer",
            "text": "A",
            "telemetry": {
                "query_dispatch_perf_ns": 100,
                "semantic_query_arrival_perf_ns": 90,
                "first_token_perf_ns": 110,
                "response_completion_perf_ns": 120,
            },
        },
        {
            "record_id": "qa",
            "kind": "answer",
            "text": ".",
            "telemetry": {
                "query_dispatch_perf_ns": 100,
                "semantic_query_arrival_perf_ns": 90,
                "response_completion_perf_ns": 130,
            },
        },
    ]
    result = summarize_telemetry(events, [{"record_id": "qa", "status": "completed"}])
    assert result["responsiveness"]["ttft_ms"]["population_count"] == 1
    assert result["telemetry_coverage"]["query_ttft"] == 1.0


def test_judge_env_prefers_trace_names_and_falls_back_to_osb(monkeypatch):
    monkeypatch.delenv("TRACE_VLM_JUDGE_BASE_URL", raising=False)
    monkeypatch.setenv("OSB_VLM_JUDGE_BASE_URL", "http://legacy:1/v1")
    assert judge_from_settings({}).base_url == "http://legacy:1/v1"

    monkeypatch.setenv("TRACE_VLM_JUDGE_BASE_URL", "http://primary:1/v1")
    assert judge_from_settings({}).base_url == "http://primary:1/v1"


def test_judge_api_key_reads_legacy_osb_name(monkeypatch):
    monkeypatch.delenv("TRACE_VLM_JUDGE_API_KEY", raising=False)
    monkeypatch.setenv("OSB_VLM_JUDGE_API_KEY", "legacy-key")
    router = judge_from_settings({})
    assert router.api_key_env == "TRACE_VLM_JUDGE_API_KEY"
    assert router.vlm.api_key == "legacy-key"

    monkeypatch.setenv("TRACE_VLM_JUDGE_API_KEY", "primary-key")
    assert judge_from_settings({}).vlm.api_key == "primary-key"
