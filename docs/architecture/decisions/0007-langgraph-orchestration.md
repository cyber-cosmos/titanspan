# ADR 0007: LangGraph Orchestration

- Status: Accepted for the planned workflows module
- Date: 2026-11-24

## Context

The future AI workflow layer needs stateful graph execution, checkpointing,
interruption, and resumption. Reimplementing a graph runtime would duplicate
mature behavior.

## Decision

Use LangGraph as the workflow execution engine. Titanspan may add typed state,
node conventions, builders, authorization, lifecycle integration, and testing
utilities around it. Persist serializable workflow state, not live containers,
sessions, or connections.

LangGraph and LangChain are not initial dependencies. Recheck Python support,
licensing, security, and APIs when implementing the AI vertical slice.

## Alternatives considered

- A Titanspan-owned graph engine: rejected because graph execution, checkpoints,
  and recovery are foundational runtime concerns.
- A generic chain abstraction: not selected because the required stateful graph
  and interruption model is missing.

## Consequences

Preserve access to the native graph and checkpoint interfaces. Reducers and
parallel state updates need deterministic tests.

## Risks

AI libraries evolve quickly and provider behavior varies. Keep integrations
optional and do not use live commercial model APIs in default tests.

## References

- [LangGraph overview](https://docs.langchain.com/oss/python/langgraph/overview)
- [LangGraph persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
