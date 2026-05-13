# Agent evals

Behavioural tests that drive a **real LLM** through the `ConversationEngine`
and check what the agent does — which tools it calls and how it classifies
the outcome (`ChatResponse.scenario`).

Distinct from `tests/`:

|                    | `tests/`                          | `evals/`                            |
| ------------------ | --------------------------------- | ----------------------------------- |
| LLM                | Mocked (`ScriptedChatModel`)      | Real (`ChatOpenAI`)                 |
| Determinism        | Deterministic                     | Stochastic, even at `temperature=0` |
| Cost               | Free                              | Pays per API call                   |
| Cadence            | Every PR                          | On demand / nightly                 |
| Failure means      | Code broke                        | Prompt/model regression, or noise   |

## Running

```bash
# Run the whole eval suite
OPENAI_API_KEY=sk-... pytest evals/ -v

# Aggregate-only output (pass/fail counts, no tracebacks)
OPENAI_API_KEY=sk-... pytest evals/ --tb=no -q

# Run one case
OPENAI_API_KEY=sk-... pytest evals/ -k semantic-search

# Try a different model
EVAL_MODEL=gpt-5.4 pytest evals/
```

Skipped automatically if `OPENAI_API_KEY` is not set (so the suite stays
silent on CI without secrets).

## Reading results

Treat each case as a *signal*, not a hard gate. A single flip after a prompt
edit doesn't necessarily mean the prompt is worse — re-run it. A *pattern*
of flips (e.g., every `lookup` case fails) is a real regression.

Useful follow-ups when a case fails:
1. Read the printed `message` and `scenario` from the failure — was the
   routing actually wrong, or did the model phrase a borderline case
   differently?
2. Re-run with `-v` to see which tool the agent picked instead.
3. If multiple runs disagree, increase the case set so aggregate accuracy
   becomes the metric rather than per-case pass/fail.

## Adding cases

`ROUTING_CASES` in `test_agent_routing.py` is just a parametrize list. Add a
tuple of `(user_input, expected_tools, expected_scenario)` and re-run. Aim
for breadth: at least one case per tool and per scenario tag.

Multi-turn flows live as their own tests (see
`test_update_previous_field_across_turns`, `test_save_requires_explicit_confirmation`).
