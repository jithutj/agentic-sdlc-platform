# Manual Windmill connector

[red5_linear_dispatch.py](red5_linear_dispatch.py) is the single reviewed manual connector for this integration. Import it as a Python script in a restricted local Windmill Community workspace. Its only argument is the allowlisted issue identifier. It uses Windmill-managed secret variables and a fixed private intake URL; no polling schedule, incoming webhook, arbitrary URL, shell operation or approval action is provisioned.

The script fetches identity-only Linear data, validates the configured organization/team/issue/project binding, sends a fixed A1 draft contract, and returns safe run/thread/status diagnostics. FastAPI independently validates authorization and Linear identity, then delegates to the existing persistent graph. Job retries are separate from agent resume and cannot issue approvals.

Use [local deployment](../docs/development/deployment.md) for services/networks, and load the [project pilot runbook](../docs/projects/redeeming-light/pilot.md) only when configuring that pilot. Unit tests mock HTTP. [The acceptance harness](../scripts/verify_red6.py) executes this script in a real worker with an explicit test-only Linear response substitution. See [evidence](../docs/development/red6-validation.md) before making live-integration claims.
