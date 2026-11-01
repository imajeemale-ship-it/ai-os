# Signal Watch portable launch configuration

The existing `apps/signal-watch/scripts/install-launch-agent.sh` is **machine-specific**. It contains an absolute checkout path, an absolute local Supervizor path, and a fixed chat-filter list. It also installs and starts a macOS LaunchAgent, so **do not run it as a portfolio demo**.

This document is a configuration template, **not an installer**. It does not change the existing script, start a service, or require credentials.

## Configuration to supply on another Mac

| Setting | Purpose | Recommended source |
|---|---|---|
| `REPO_ROOT` | Absolute checkout directory | Resolve from the installed checkout |
| `PYTHON_BIN` | Python interpreter | Explicit executable path |
| `STATE_DIR` | State and logs | `$HOME/.ai-os` |
| `SIGNAL_WATCH_SUPERVIZOR_ROOT` | Optional local Supervizor data | User-configured path |
| `TELEGRAM_BOT_TOKEN` | Bot credential | Secure local secret store or protected environment file |
| `TELEGRAM_CHAT_ID` | Delivery destination | Local configuration |
| `SIGNAL_WATCH_CHATS` | Monitored chat filters | User-provided list; not hard-coded into a generic example |

**Security:** Never commit live tokens, chat IDs, private-group content, or a generated environment file. The existing installer writes a protected environment file using `umask 077` and `chmod 600`, but its configuration values and shell interpolation should be reviewed before a generalized replacement is deployed.

## Safe replacement acceptance criteria

1. Resolve paths without assuming a particular macOS username.
2. Preserve current service behavior and existing LaunchAgent label unless a migration is explicitly authorized.
3. Validate required configuration and escape values correctly for shell and plist contexts.
4. Test generation of a plist in a temporary directory **without** calling `launchctl`.
5. Confirm no credentials or private chat content enter stdout, logs, tests, or version control.
6. Test actual service installation only with explicit operational approval.

**Status:** documentation-only portability design. The existing service and installer are unchanged.
