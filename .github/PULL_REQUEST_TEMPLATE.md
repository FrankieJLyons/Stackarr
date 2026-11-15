## Problem and result

## Validation

- [ ] `ruff check stackarr tests tools`
- [ ] `pytest -q`
- [ ] Browser smoke test (when UI changed)
- [ ] Dependency and source audit

## Safety review

- [ ] No live media stack was contacted
- [ ] No secrets, personal paths, or deployment-specific assumptions added
- [ ] External application writes are explicit, bounded, and audited
