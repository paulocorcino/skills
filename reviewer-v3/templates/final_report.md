# Review - <target>

verdict: <BLOCKED | APPROVED-WITH-FIXES | APPROVED>
scope: <full | partial(<one-phrase reason>)>
base: <base>
checks: <executed summary>
not exercised: <checks/lanes/runtime surfaces with reasons, or none>

## Findings

1. [HIGH|MEDIUM|LOW] <file:line | spec-ref | command> - <problem>
   impact: <why it matters>
   fix: <concrete fix>

## Coverage

excluded:
  - <path> (<reason>)

not-reviewed:
  - <path> (<reason>)

## Open Questions

- <question, or omit section if empty>

## Verification

- <command/check>: <pass|fail|not run> - <short evidence or reason>

## Notes

Notes accepts only: scope limits, skipped checks, adjudication caveats, evidence caveats. Praise, "strong positives", strengths, and positive summaries are forbidden.
