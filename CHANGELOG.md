# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-05-10

### Added

- **Rebranded to QuartoRef**: Renamed the project from QuartoPmid to QuartoRef to reflect support for multiple reference types.
- **DOI Support**: Full support for `[@doi:ID]` tags.
- **Enhanced Metadata Syncing**: Implemented DOI metadata fetching via Content Negotiation (doi.org/Crossref).
- **Dotenv Support**: Integrated `python-dotenv` for easier configuration management.
- **Polite Pool Support**: Added `email` setting for DOI API limits.
- **Semicolon Encoding**: Supports `%3B` encoding for DOIs containing semicolons.
- **Normalization Engine**: Automatically lowercases DOI IDs and removes trailing punctuation.
- **Improved API Clients**: Refactored `PubMedClient` and `DoiClient` with specialized rate limiting and robust error handling.

### Changed

- **Tag Format (Breaking Change)**: The prefix (`pmid:` or `doi:`) is now mandatory. Legacy prefix-less tags like `[@12345]` are no longer supported.

## [1.1.0] - 2026-05-09

### Added

- **Automatic CSL Download**: Restored the ability to parse the `csl:` field in YAML front matter and automatically download the CSL file.
- **GUI Dialog Fallback**: Restored the file selection dialog using `tkinter`.
- **Extended CLI Options**: Added `--download-csl` / `--no-download-csl` flags.

## [1.0.0] - 2026-05-09

### Added

- **Initial Release (as QuartoPmid)**: Fully supports the standard Quarto citation syntax `[@123456]`.
- **Automatic YAML Update**: Safely appends or merges the generated JSON file into the `bibliography:` field.
- **Safe Overwriting**: Automatically creates a `.bak` backup.
