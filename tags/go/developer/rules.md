Use these rules when the target project is a Go codebase.

## Project organization

- A package should either contain small single-file structures or one main structure where each file contains a separate public method.
- For structures with up to three public methods, keeping them in one file is acceptable if that is already the local convention.
- Keep dependency interfaces in `external.go` for the service or component they belong to.
- `external.go` should contain only dependency interfaces.
- Dependency interfaces in `external.go` should be public and named in PascalCase.
- When the project uses generated mocks, keep generated or maintained mocks in `mock/external.go`.
- When the project uses mock generation directives, keep the `//go:generate mockgen ...` directive as the first line of `external.go`.
- After changing `external.go`, run the repository's code generation command; in acquiring-style repositories this is `task generate`.
- The main structure should live in its own file.
- Place the constructor `New<TypeName>` directly under the main structure.
- `New<TypeName>WithDeps` is acceptable when the default constructor creates dependencies that need to be mocked in tests.
- Keep shared private helpers, constants, and variables used across several public-method files in the file with the main type.
- Service packages should depend only on external packages and the repository's shared internal layers such as domain, utils, and config when the project is organized that way.
- Keep shared domain models in the project's shared domain layer when such a layer exists.
- Keep non-business utility code in the project's utility layer.
- Generic utility helpers should live in the repository's generic utility area when the codebase has one.
- For provider-style architectures, preserve the split between client, factory, terminal, or equivalent responsibilities.
- When working with repositories, SQL, or storage models, verify the storage structure against migrations if migrations are the source of truth in that repository.

## File and type organization

- Keep global variables at the top of the file.
- Place constants and types near the top of the file after globals.
- Preferred file order is: globals, constants and types, main type, public methods, then private methods in call order from top to bottom.
- Use stable casing for abbreviations such as `ID`, `URL`, `HTTP`, `API`.
- Place method-specific constants at the top of that method's file.
- Place constants shared by several methods at the top of the main type file.

## Code structure

- Keep a private method directly below the public method that uses it when it is local to that flow.
- If a private method is used by several public methods, move it near the main structure instead of duplicating it.
- Shared reusable structures used in several packages should live in the repository's shared domain layer.
- Static helper functions should contain minimal logic; if a helper grows substantial logic or gains dependencies, move it into a struct that can be mocked and tested explicitly.

## Error handling

- Error text must explain where and what failed in readable language.
- Do not put file names, tags, or opaque technical markers into the error text.
- Do not build dynamic input data directly into error strings unless the local project explicitly does so.
- Limited enum-like values may appear in an error message only when truly necessary and kept minimal.
- If a function creates a new error, wraps an error, or returns an error from an external package or static helper, log it with useful debugging metadata before returning when the repository expects operational logging at that boundary.

## Logging

- Log context that helps diagnose the failed operation: action, step, identifiers, codes, or types as appropriate for the project.
- Keep log messages readable and action-oriented.
- Do not put file names, tags, or opaque technical markers into the log message text.
- Prefer the repository's canonical structured logging fields and helper tags when they exist.
