## Exchange Buy QA Stand Validation

Validate the deployed changes by running the exchange buy Playwright scenario.

Run the `/pw-exchange-buy` skill with these arguments, taking values from `release_context` in the context:

```
/pw-exchange-buy \
  --stand {release_context.target_branch} \
  --dataset {release_context.dataset}
```

The skill registers a user, passes KYC, and completes a crypto purchase with a card.
If the skill exits with an error or any step fails — the stage is failed.
