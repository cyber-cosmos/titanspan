# ADR 0017: Domain-oriented shared contracts

- Status: Accepted
- Date: 2026-11-25

## Context

Shared contracts had been collected in flat modules while logging protocols
lived under the logging component. That split made ownership unclear and
prevented core components from depending on one consistent shared boundary.
Some logging protocols imported concrete logging types, which also made a
direct move into the Contracts component create dependency cycles.

## Decision

- Organize shared protocols under domain packages in `titanspan.contracts`.
  The established domains are `config`, `container`, `logging`, and `support`.
- Keep each contract declared once. The top-level Contracts package and
  component packages may re-export the canonical object, but do not define
  duplicate protocols.
- Make logging contracts generic over record and logger types so the shared
  package does not import concrete logging implementations.
- Keep component-private protocols next to the implementation they describe.
  Add a new domain package only when there is a real shared boundary.
- Remove the former flat module import paths from this pre-release API. The
  supported convenience imports remain the Contracts root, domain package,
  and relevant component package.

## Consequences

Framework modules can import contracts without depending on concrete
components. Contract ownership and public identity are testable. Consumers of
unreleased direct imports such as `titanspan.contracts.config_repository` or
`titanspan.logging.contracts` must update to the domain packages or supported
component exports.

The domain organization does not imply that all framework components exist.
Contracts for unimplemented modules remain deferred until their owning
architecture and semantics are established.

## Verification

`tests/unit/contracts/test_contract_organization.py` checks declaration
ownership and object identity across root and component re-exports. Strict
Pyright verifies that concrete logging implementations satisfy the generic
protocols. Component integration suites verify behavior at implementation
boundaries.
