# blender-lesson-renderer

## ADDED Requirements

### Requirement: Spec validation
The renderer SHALL reject a lesson spec that does not validate, and SHALL name the
offending field in the error. Scene ids MUST be unique and listed in ascending order.

#### Scenario: duplicate scene ids
- **WHEN** two scenes share an id
- **THEN** loading fails with a `SpecError` that names the uniqueness rule

### Requirement: Draft gate
The renderer SHALL refuse to render a lesson whose status is `draft` unless the
operator passes `--allow-draft`. Dry-run planning SHALL remain available for drafts.

#### Scenario: unapproved script
- **WHEN** a draft lesson is rendered without the override
- **THEN** the renderer exits with code 2 and does not invoke any external tool

### Requirement: Deterministic rendering
Given the same spec, script version and tool versions, the renderer SHALL produce the
same frames. Its provenance record SHALL include the spec SHA-256, the render script
SHA-256 and the Blender version.

#### Scenario: provenance pins the artifact
- **WHEN** a render completes
- **THEN** `provenance.json` records the spec hash, render script hash, Blender version
  and the SHA-256 of `lesson.mp4`

### Requirement: Failure isolation
A failing stage SHALL stop the run and SHALL NOT leave a video that reports success.

#### Scenario: Blender fails
- **WHEN** Blender exits non-zero or writes the wrong number of frames
- **THEN** the renderer exits with code 4 and writes no `provenance.json`
