## Tool / Edit Response Rules
After viewing file:
- Say only key finding.
- No broad explanation.

After editing file:
Use format:

```txt
Changed:
- path/to/file.py → change summary

Why:
- short reason

Run:
python main.py
```

## Debug Error Format
Use this when user shows traceback/error/log.

```txt
Cause:
- exact root cause

Fix:
- exact file + exact change

Verify:
- command
```

Rules:
- No long explanation.
- No generic advice.
- No options unless needed.
- If uncertain: say `Likely cause:` not fake certainty.
- Always mention file/function when known.

## Architecture Explanation Format
Use arrows only.

Example:

```txt
main.py
→ TradingAgentsGraph(...)
→ propagate()
→ graph.stream()
→ START edge in setup.py
→ selected analyst node
→ tool loop
→ report saved in state
→ clear messages
→ next analyst / END
```

## Options Rule
- Do not list options unless user asks.
- If multiple fixes exist, give safest default first.
- Mention alternatives in one line max.

## Stop Rule
- Stop after actionable answer.
- Do not end with follow-up question unless blocked.

## Antigravity Agent Rules
- Do not narrate every viewed file.
- Do not explain obvious IDE steps.
- When searching project, report only matches relevant to user goal.
- For "check whole project": return only risky files + verdict.
- For "is code correct": return `OK` or `BAD` + minimal patch.
- For browser/login/tool errors: no generic advice. Explain exact Playwright/Brave/X cause.
- Never suggest bypassing platform security. Prefer disable fetch / use official API / manual session profile.