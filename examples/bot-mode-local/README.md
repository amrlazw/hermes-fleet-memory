# Bot Mode, locally: two nodes talking without a human relay

A rehearsal of Fleet Memory nodes messaging each other directly, using Hermes's
built-in Bot Mode and `hermes peer`. It runs two sandboxed Hermes gateways on one
machine, a stand-in **Chester** and a stand-in **Winston**, and lets them talk.

```bash
python examples/bot-mode-local/run_demo.py \
    --model-config ~/.hermes/config.yaml --api-key-env MY_ROUTER_KEY
python examples/bot-mode-local/run_demo.py --demo    # run the conversation again
python examples/bot-mode-local/run_demo.py --stop    # stop both gateways, delete the sandbox
```

`--model-config` picks the config whose `model:` block the sandboxes copy.
`--api-key-env` names an environment variable holding that model's key, so the
key never appears on a command line.

## What it isolates

| | |
|---|---|
| Hermes home | Each node gets its own `HERMES_HOME` in your temp folder. Your real install is never read for anything but the `model:` block. |
| Network | API servers bind `127.0.0.1:18642` and `:18643` only. |
| Environment | Sandboxes get an allowlist of system variables, never a copy of yours. |
| Tools | No shell, file, web, browser or messaging-platform tools, only Bot Mode's `message_agent`. |
| Platforms | If a sandbox log shows Telegram, Discord, Slack or similar, the script stops both gateways. |

The environment allowlist exists because the first version copied `os.environ`.
That handed a real `TELEGRAM_BOT_TOKEN` to a sandbox gateway, which started
polling the real bot until Telegram refused it with a getUpdates conflict.

## What a run looks like

Demo 1 sends one message with `hermes peer dm`. Demo 2 asks Chester's agent to
find something out from Winston on its own, using `message_agent`. From the first
run against a local 9router (timestamps from the sandboxes' session databases):

```
00:28:34  chester -> winston   Two fleet_health_ping tasks are queued for you. Can you take a gpu_batch tonight, on which GPU?
00:28:38  winston  calls message_agent(target="chester")          <- replies on its own initiative
00:28:47  chester receives     "I can take the gpu_batch tonight after 22:00, on my RTX 3070 Ti ..."
00:28:54  chester  calls message_agent(target="winston")          <- acknowledges, mentions the queued pings
00:29:01  operator -> chester  Find out Winston's GPU and free time. Ask him, wait, summarise.
00:29:10  chester  calls message_agent(target="winston")
00:29:17  winston  calls message_agent(target="chester")
00:29:22  chester receives     "My GPU is an RTX 3070 Ti ... available tonight anytime after 22:00."
```

## Known rough edges

- **Replies are fire-and-forget.** A sender learns the outcome from a background
  completion notice, or by polling with the `process` tool. That tool is part of the
  `terminal` toolset, which this demo disables, so Chester cannot wait for the reply
  and may report "Winston confirmed" a moment before the confirmation lands.
- **Acknowledgement ping-pong.** Both agents answer each message with another
  message. They settle after a few rounds, but a real fleet needs a norm such as
  "do not reply to a pure acknowledgement".
