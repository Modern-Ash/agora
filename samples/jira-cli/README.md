# Jira ACLI adapter sample

This sample installs the reviewed Jira adapter and prepares native Atlassian CLI search and
transition commands. It runs without ACLI because it does not use `--launch`.

The Product Owner receives issue transition authority from the active Scrum role. The Developer can
search Jira but cannot comment because installing the adapter does not grant `issue.write`.

Run it from the repository root:

```bash
uv run python samples/jira-cli/run.py
```

For live execution, install ACLI, authenticate the intended Jira site outside Agora, inspect the
prepared command, and then invoke with `--launch`.
