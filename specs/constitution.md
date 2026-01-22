<!--
=============================================================================
SYNC IMPACT REPORT
=============================================================================
Version change: N/A → 1.0.0 (Initial creation)

Modified principles: N/A (first version)

Added sections:
- Core Principles (5 principles)
- Development Standards
- Quality Assurance
- Governance

Removed sections: N/A

Templates requiring updates:
- ✅ specs/templates/plan-template.md (downloaded, no changes needed)
- ✅ specs/templates/spec-template.md (downloaded, no changes needed)
- ✅ specs/templates/spec-checklist.md (downloaded, no changes needed)
- ✅ specs/templates/tasks-template.md (downloaded, no changes needed)

Follow-up TODOs: None
=============================================================================
-->

# Omni Agent Constitution

## Core Principles

### I. Modular Architecture

System MUST follow a modular, pluggable architecture:
- Core functionality separated into independent components (Agent, Tools, MCP, Skills)
- Each component MUST be independently testable and replaceable
- Tools MUST inherit from `Tool` base class with standardized interface (`name`, `description`, `parameters`, `execute`)
- MCP servers MUST be configurable via `mcp.json` without code changes
- Skills MUST be self-contained directories with `SKILL.md` definition

**Rationale**: Modularity enables isolated testing, parallel development, and easy extension without modifying core code.

### II. Test-First Development (NON-NEGOTIABLE)

All new features and bug fixes MUST follow test-driven development:
- Write failing tests before implementation
- Tests MUST cover contract (API surface), integration (workflows), and unit (logic) levels
- Use `pytest` with async support (`pytest-asyncio`)
- Minimum test coverage for new code: 80%
- Red-Green-Refactor cycle strictly enforced

**Rationale**: Tests serve as executable documentation and prevent regressions. TDD ensures code is designed for testability.

### III. Observability First

Every execution path MUST be observable:
- AgentLogger MUST record: STEP (token usage), REQUEST, RESPONSE, TOOL_EXECUTION (timing), COMPLETION
- Langfuse integration for production tracing when `LANGFUSE_ENABLED=true`
- TraceLogger for multi-agent workflow tracking
- Token usage MUST be tracked and reported per step
- Tool execution time MUST be measured in milliseconds

**Rationale**: Production systems require visibility into behavior. Observability enables debugging, optimization, and cost tracking.

### IV. Simplicity & YAGNI

Start simple, add complexity only when justified:
- No premature abstractions - wait for the third use case
- Direct implementation over patterns unless pattern solves a current problem
- Avoid feature flags and backward-compatibility shims when direct changes suffice
- Delete unused code completely - no `_unused` variables or `# removed` comments
- Comments explain "why", not "what" - code should be self-descriptive

**Rationale**: Complexity is the enemy of maintainability. Simple code is easier to understand, test, and modify.

### V. Provider Agnostic Design

System MUST remain independent of specific LLM providers:
- LiteLLM abstraction MUST handle all provider-specific details
- Model names MUST use `provider/model` format for standardization
- Auto-adaptation of parameters (`max_tokens`, etc.) to provider limits
- No provider-specific code in business logic
- Configuration-driven provider selection via `.env`

**Rationale**: Provider lock-in limits flexibility and increases migration costs. Abstraction enables easy provider switching.

## Development Standards

### Code Organization

- Source code MUST reside in `src/omni_agent/`
- Tests MUST reside in `tests/` with mirrored structure
- External skills in `./skills/`
- Agent workspace in `./workspace/`
- Logs in `~/.omni-agent/log/`

### Dependency Management

- Use `uv` as package manager
- Dependencies declared in `pyproject.toml`
- Pin exact versions for production dependencies
- Development dependencies separate from runtime

### API Design

- RESTful endpoints via FastAPI
- OpenAPI documentation auto-generated
- Request/response schemas via Pydantic
- Streaming via Server-Sent Events (SSE)
- ACP protocol compliance for editor integration

## Quality Assurance

### Code Review Requirements

- All PRs MUST verify constitution compliance
- No merge without passing CI (lint, format, type check, tests)
- Complexity additions require justification in PR description
- Security review for auth/sandbox/external data handling

### Testing Gates

| Gate | Requirement |
|------|-------------|
| Lint | `ruff check` passes |
| Format | `ruff format --check` passes |
| Type | `pyright` or type annotations verified |
| Unit | `pytest tests/` passes |
| Coverage | 80%+ for new code |

## Governance

This constitution supersedes all other development practices for the Omni Agent project.

**Amendment Process**:
1. Propose changes via PR to `specs/constitution.md`
2. Document rationale and impact in PR description
3. Require at least one approving review
4. Update `CONSTITUTION_VERSION` per semantic versioning:
   - MAJOR: Principle removal/redefinition
   - MINOR: New principle or section
   - PATCH: Clarification or typo fix
5. Update `LAST_AMENDED_DATE`

**Compliance Review**:
- All PRs MUST reference constitution compliance
- Violations MUST be justified with documented trade-offs
- Use CLAUDE.md for runtime development guidance

**Version**: 1.0.0 | **Ratified**: 2025-01-22 | **Last Amended**: 2025-01-22
