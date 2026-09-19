# Executed local verification

................................................                         [100%]
- generated xml file: /Users/pavelkhudikov/PycharmProjects/AwsAgentCoreProject/SupportAgentProduction/evidence/junit.xml -
48 passed in 1.90s

Also passed: Ruff lint/format, CloudFormation schema validation for both templates, runtime module import, and deployment shell syntax.

**Environment: local injected failures, not AWS.** These are actual generated OTel IDs. AWS deployment, Docker image build, Cedar service evaluation and live cross-session memory remain unverified.

| Scenario | Trace ID | Relevant span ID | Span |
|---|---|---|---|
| tool_timeout | `0dfc3673484994cce1e6949801a2f57e` | `de536dd0a97f9054` | `gateway.attempt` |
| http_500 | `310a1b1ea8ba2e972147c2fc3545aabb` | `5a85ddfa582c8bfc` | `gateway.attempt` |
| invalid_parameters | `3fd0e158474be4f2a2380fcd4e46eede` | `34cf6ee964e9e752` | `drill.invalid_parameters` |
| wrong_tool_selection | `f470d80c2217aa094cf66c2b9b99850a` | `0656527b09209e48` | `execute_tool get_customer` |
| llm_loop | `b09751d5203a02c4b183a04e5625fe1f` | `d1234a4daccedfe2` | `execute_event_loop_cycle` |

Root causes and all parent/child spans: [local-traces.json](local-traces.json).
Test cases: [JUnit XML](junit.xml). Cloud evidence checklist: [EVIDENCE.md](../docs/EVIDENCE.md).
