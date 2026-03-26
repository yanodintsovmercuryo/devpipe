Use these rules when the target project is a Go codebase.

## Test file placement and naming

- Place tests next to the production code.
- Prefer `{source_file_name}_test.go` for tests that cover a specific source file.
- Prefer one test file per production file when the codebase follows that pattern.
- Prefer an external test package `package <name>_test` unless private symbol access is genuinely needed.

## General test structure

- Test names and `t.Run` case names should be in English.
- Call `t.Parallel()` at the top of each test function and each parallel-safe subtest when the project follows that pattern.
- Cover one public method or behavior per top-level test function.
- Use `t.Run` for scenarios inside the test.
- Do not use `init()` in `*_test.go`.
- Mark helper functions with `t.Helper()`.

## `testing_test.go` and shared fixtures

- In packages with meaningful test setup, keep shared test helpers in `testing_test.go`.
- Put shared comparers, reusable fixtures, common setup helpers, and cmp options in `testing_test.go`.
- Keep one `fixture` struct per tested service, handler, repository, or main unit.
- `setUp(t)` should return `(*fixture, func())`.
- The cleanup function should release resources such as `gomock.Controller`, temporary apps, transports, or test servers.
- Each test should create its own fixture instance so tests remain isolated and parallel-safe.
- If one package contains several independently tested structures, use separate setup helpers such as `setUpDummy`, `setUpVault`, or equivalents.

## `setUp(t)` expectations

- `setUp(t)` must call `t.Helper()`.
- Construct the tested object and all of its dependencies there.
- Prefer mocks for external dependencies unless the test intentionally exercises a real integration.
- Keep loggers, config objects, and contextual helpers lightweight and deterministic.
- Return a cleanup function and call it with `defer finish()`.
- Use `TestMain` only for truly global setup; do not replace ordinary per-test setup with `init()`.

## Mocks and dependencies

- Find dependency interfaces in `external.go` when the project uses that convention.
- Use existing mocks from `mock/external.go` when the repository generates mocks there.
- Generate mocks through the repository's generation command instead of writing them by hand.
- If `external.go` changes, rerun the generation step before trusting test compilation.
- Use only gomock for mocks in repositories that follow the acquiring style.
- Do not hand-write mocks or stubs when generated mocks are the project standard.

## `gomock` rules

- Create a fresh `gomock.Controller` per test through `setUp(t)` or the package fixture helper.
- Finish the controller through the cleanup function returned by `setUp(t)`.
- Use `.EXPECT()` to describe the behavior of real dependencies of the unit under test.
- Keep expectations local to the scenario that uses them.
- Prefer precise expectations over broad "accept anything" expectations.
- Do not mock the unit under test; mock only its external dependencies.

### Preferred matcher strategy

- Prefer exact primitive arguments where possible.
- Prefer `CMPMatch` for structs, command objects, DTOs, requests, and other rich values.
- Prefer the project's dedicated context matcher such as `MatchCtx()` for `context.Context`.
- Prefer reusable repository-level helpers over one-off matcher code in a single test.

### Forbidden weak matchers

- `gomock.Any()` is forbidden for meaningful structured inputs.
- `gomock.Any()` is forbidden for `context.Context`.
- `gomock.Any()` is forbidden when the argument content is part of the behavior being tested.
- `gomock.Any[T]()` is forbidden.
- `gomock.AnyOf()` is forbidden.
- `gomock.Not()` is forbidden.
- `gomock.Cond()` with always-true or weak conditions is forbidden.
- `gomock.AssignableToTypeOf` is forbidden unless it is truly impossible to verify the content of the value.
- `gomock.Eq` is forbidden for `context.Context` and rich structs.
- Do not use weak matchers just to make a test pass.

### Other matcher restrictions

- Avoid custom `gomock.Matcher` implementations unless no shared cmp-based helper can express the check.
- Avoid `.Do()` and `.DoAndReturn()` for argument validation when the same assertion can be encoded in the matcher itself.
- Do not hide important assertions inside callbacks if they can be expressed directly in `.EXPECT()`.

### `CMPMatch`

- If the repository already provides `CMPMatch`, use it instead of ad hoc matcher logic.
- If the repository does not yet provide `CMPMatch`, add it in the shared test helper area.
- `CMPMatch` should compare values through `cmp` with explicit options and produce readable mismatch output.
- `CMPMatch` is the default way to express structured gomock argument expectations in projects following this style.

## Assertions and comparisons

- Use the repository's preferred assertion library and comparison helpers.
- For primitives and simple values, prefer `require/assert` helpers such as:
  - `require.Equal`
  - `require.NotEqual`
  - `require.True` / `require.False`
  - `require.NoError`
  - `require.Error`
  - `require.ErrorIs`
  - `require.ErrorContains`
  - `require.Empty` / `require.NotEmpty`
  - `require.Nil` / `require.NotNil`
- Do not use `require.Equal` or `assert.Equal` for structs when the project expects cmp-based comparison.
- In Go projects following the acquiring style, almost all non-trivial comparisons should go through `cmp`.

## `cmp` and `cmpopts` rules

- Treat `cmp` as the default comparison mechanism for almost all rich values.
- Use project-level wrappers such as `CMPEqual` and `CMPMatch` instead of open-coding comparison logic in each test.
- Centralize reusable `cmp.Comparer` and `cmp.Option` values in `testing_test.go`.
- Keep canonical cmp option groups in helper functions such as `cmpComparers()` when the package has many repeated comparisons.
- If the project has a canonical `testDuration`, keep time-based comparisons aligned with it.

### What should go through `cmp`

- Structs and nested structs.
- Request and response payloads.
- Command objects and DTOs.
- Collections of rich values.
- Mock expectations for non-trivial arguments.
- Errors when compared as part of larger structures.

### Standard helpers to use or add

- `CMPEqual` for explicit assertions in tests.
- `CMPMatch` for gomock expectations and matcher-based comparisons.
- `MatchCtx()` or the repository's equivalent helper for `context.Context`.
- A reusable error comparer based on `err.Error()` or the repository's approved error semantics.

### Allowed `cmp`/`cmpopts` options

- `cmpopts.EquateApproxTime(testDuration)` for time values.
- `cmp.Comparer(...)` for complex domain-specific comparison.
- `cmpopts.IgnoreUnexported(Type{})` for types with unexported fields.
- `cmpopts.IgnoreFields(...)` only in tightly constrained last-resort cases.
- `cmpopts.SortSlices(...)` when slice order is irrelevant.
- `cmpopts.EquateEmpty()` when nil and empty slices/maps should be equivalent.
- `cmpopts.SortMaps(...)` when map key order needs normalization.

### `cmpopts` guidance

- Keep `testDuration` centralized in `testing_test.go`; the acquiring convention is `5 * time.Second`.
- Do not ignore time fields through `IgnoreFields`; use `EquateApproxTime`.
- Prefer `cmp.Comparer` first and `cmpopts.IgnoreUnexported(Type{})` second for errors and types with unexported fields.
- `cmpopts.IgnoreUnexported` must receive the struct type, not a pointer.
- For `http.Request` and `http.Response`, use `cmpopts.IgnoreUnexported(http.Request{})` and `cmpopts.IgnoreUnexported(http.Response{})` when needed.
- Use `cmpopts.IgnoreFields` only as a last resort for truly unstable dynamic fields such as generated UUIDs, `RequestID`, `ClientRequestID`, or fields created dynamically inside the tested method.
- Do not reach for `IgnoreFields` to paper over incomplete expectations.
- Prefer explicit comparers and helper options over broad ignore-based matching.

### `cmp.Comparer` guidance

- Use `cmp.Comparer` for error comparison via `Error()`.
- Use `cmp.Comparer` for types where comparison logic is meaningful and can be expressed explicitly.
- Prefer `cmp.Comparer` over `IgnoreFields` because it checks content instead of skipping it.
- Move reusable comparers into `testing_test.go`.

### Comparison-specific prohibitions

- `cmp.Diff` is forbidden directly in ordinary assertions when wrappers such as `CMPEqual` exist.
- `cmp.FilterPath` is forbidden.
- Do not compare rich structs through `require.Equal`.
- Do not use `reflect.DeepEqual` or other reflection-based comparison patterns.
- Do not use the `reflect` package in tests for comparison or type tricks; prefer `cmp.Comparer` and `cmpopts.IgnoreUnexported`.
- Do not bypass cmp-based helpers in mocks by falling back to weak gomock matchers.
