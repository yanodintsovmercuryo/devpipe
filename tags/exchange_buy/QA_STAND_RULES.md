## Exchange Buy QA Stand Validation

Run the Playwright exchange buy scenario using the `/pw-exchange-buy` skill.

Pass the following parameters from `release_context`:
- `dataset` — test dataset for the flow (e.g. `s4-3ds`)
- `target_branch` — deployed stand (e.g. `u1`)
- `service` — service name

The skill registers a user, passes KYC, and completes a crypto purchase with a card.
The run must complete without errors for the stage to be considered passed.
