# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.1.0] - 2026-05-09

### Added

- **Automatic CSL Download**: Restored the ability to parse the `csl:` field in YAML front matter and automatically download the CSL file from the official repository if it's missing locally.
- **GUI Dialog Fallback**: Restored the file selection dialog using `tkinter` for environments where TTY (interactive shell) is unavailable or when explicitly requested.
- **Extended CLI Options**: Added `--download-csl` / `--no-download-csl` flags to control the automatic CSL download behavior.

### Fixed

- **Improved Dependency Checks**: Added clearer instructions when `requests` or `ruamel.yaml` are missing.
- **Robust PMID Extraction**: Fine-tuned the regex logic for more reliable PMID detection and extraction.

## [1.0.0] - 2026-05-09

### Added

- **Quarto Native Support**: Fully supports the standard Quarto citation syntax `[@123456]`. Implemented smart merging for consecutive tags like `[@123] [@456]` into `[@123; @456]`.
- **Automatic YAML Update (`--update-yaml`)**: Safely appends or merges the generated JSON file into the `bibliography:` field without breaking existing comments or formatting (using `ruamel.yaml`).
- **Safe Overwriting**: Automatically creates a `.bak` backup before modifying the original manuscript.
- **Idempotency**: Skips file writes if no changes are detected in the document.

### Changed

- **Independent Repository & Scope Refinement**: Forked from `PyRefPmid` and rebranded as `QuartoPmid`, focusing exclusively on Quarto workflows.
- **Removed CSL/Pandoc Dependencies**: Delegated styling and rendering responsibilities entirely to Quarto. Adhered to the Single Responsibility Principle (SRP), resulting in a much lighter tool.
- **Revamped CLI**: Improved the Command Line Interface for better usability, removing unnecessary GUI elements from the core flow.

### Removed

- Dropped support for legacy citation formats (e.g., `[pmid: 123]`) to focus on Quarto standards.
- Removed automatic CSL downloading (initially removed in 1.0.0, then restored in 1.1.0 with better control).
- Removed the automatic Pandoc execution process.
