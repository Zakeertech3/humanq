# Claude Code gate

Hold risky Bash commands on the humanq board until a human answers. Claude Code asks,
you approve or deny from the board, and the tool call continues or stops.

Ordinary commands are untouched. Only commands matching a risky pattern reach the board.

## Setup in five steps

### 1. Start the board

```
uv run python -m board.main
```

It listens on `BOARD_HOST` and `BOARD_PORT` from your `.env`, by default
`http://localhost:8000`. Open that URL and sign in with your `BOARD_ADMIN_KEY`.

### 2. Register an agent and copy the key

```
curl -s -X POST http://localhost:8000/agents \
  -H "Authorization: Bearer $BOARD_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"name": "claude-code", "harness": "claude-code"}'
```

The reply contains `api_key`, a string starting with `hq_`. It is shown once and only
its hash is stored, so copy it now.

### 3. Set the environment variables

```
export HUMANQ_URL=http://localhost:8000
export HUMANQ_API_KEY=hq_the_key_from_step_2
```

Optional:

| Variable | Default | Meaning |
| --- | --- | --- |
| `HUMANQ_GATE_TIMEOUT` | `240` | Seconds to wait for a human before denying |
| `HUMANQ_GATE_PATTERNS` | see below | JSON array of regexes that count as risky |

The default patterns are `git push`, `rm` with recursive and force flags, `docker`,
`curl` with `-X` or `--request` set to POST, PUT or DELETE, and anything mentioning
`.env`.

### 4. Install the hook

Copy the contents of `settings.snippet.json` into `.claude/settings.json`. If that file
already has a `hooks` block, merge the `PreToolUse` entry into it rather than replacing
the whole block.

### 5. Test it with something harmless

```
docker ps
```

`docker` is a default pattern, but `docker ps` changes nothing. Claude Code will pause,
a request appears on the board titled `Run: docker ps`, and the command runs only after
you resolve it with `allow`. Resolve it with anything else and the command is blocked.

## The two timeouts

There are two, and the hook timeout must be the larger one:

- `HUMANQ_GATE_TIMEOUT` (default 240s) is how long the gate waits for you.
- `"timeout"` in the settings snippet (300s) is how long Claude Code waits for the gate.

If the hook timeout were the smaller of the two, Claude Code would kill the gate while
it was still waiting for you, and you would lose the decision. Keep at least a minute
between them, and raise both together if you want longer to think.

## Failure behaviour

The gate denies rather than allows whenever it cannot get an answer: no board reachable,
no key configured, a malformed payload, or your timeout expiring. It also exits with
code 2 on a deny, because Claude Code treats every exit code other than 0 and 2 as a
non-blocking error and would let the command through.
