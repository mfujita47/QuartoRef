# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.6.0] - 2026-06-11

### Fixed

- **HTTP 403 Forbidden Bypass for PMC/PubMed**: Replaced the third-party `requests` library with Python's built-in `urllib.request` in the citation fetcher. This successfully bypasses Web Application Firewall (WAF) and CDN blocks (such as JA3 TLS fingerprint blocks) that target the `urllib3`/`requests` TLS signature on NCBI/PMC APIs, restoring normal metadata retrieval.

## [1.5.0] - 2026-06-01

### Added

- **Bibliography Pruning**: The synchronization engine now automatically filters and removes (prunes) cached bibliography records from the generated CSL-JSON file if they are no longer actively cited in the manuscript, keeping the citation database clean.
- **Verbose Diagnostic Mode**: Added a new `--verbose` CLI flag (enabled by default) that outputs real-time API fetch states (e.g. `[1/2] Fetching doi:10.1000/xyz... Success: ...`) and secure masked confirmation of loaded API keys.

### Changed

- **Safe Sequential Fetching**: Replaced the multi-threaded concurrent engine with a highly robust sequential, single-threaded fetch loop. Added a `1.0s` polite sleep delay between multiple API requests to safely avoid `429 Too Many Requests` rate limit flags on free tiers.
- **Enhanced CSL Normalization**:
  - Automatically translates Crossref and PubMed item types into standard CSL-JSON compatible fields (e.g. `journal-article` -> `article-journal`, `book-chapter` -> `chapter`, `proceedings-article` -> `paper-conference`).
  - Cleans up journal short abbreviations (`container-title-short`) by stripping periods and trimming spaces (e.g. `Proc. Natl. Acad. Sci. U.S.A.` -> `Proc Natl Acad Sci USA`).
  - Gracefully handles missing citation fields (e.g., automatically populates missing authors with `UNKNOWN AUTHOR`).
  - Stores standard, valid error JSON structures for failed requests, preventing Quarto rendering failures while keeping diagnosis clear.
- **Reduced Dependency Footprint**: Removed the `shutil`, `concurrent.futures`, and complex HTTP retry adapter configurations, rewriting backup and filesystem sync logic using standard library file operations for a lighter weight, maintenance-friendly design.

## [1.2.2] - 2026-05-10

### Added

- **Production-Ready Robustness**: Implemented extensive error handling for file I/O and API requests to ensure stable operation in all environments.
- **Improved YAML Handling**: Enhanced frontmatter detection and update logic using regular expressions, preventing duplication and ensuring correct placement even with BOM or leading spaces.
- **Detailed Error Reporting**: API fetch failures now include specific HTTP status codes (e.g., 404, 403) for easier troubleshooting.
- **Better Cancellation UX**: Added a graceful exit (with status code 0) when a user cancels file selection via `Ctrl+C`.

### Changed

- **Consolidated CLI Options**: Simplified command-line interface by moving configuration like API keys and email to `.env` files (recommended) or environment variables.
- **Internal Refactoring**: Major architectural cleanup to improve performance, thread safety, and long-term maintainability.

## [1.2.1] - 2026-05-10

### Fixed

- **CSL-JSON Normalization**: Fixed "expected String or Number, but encountered Array" error during Quarto rendering by ensuring fields like `ISSN`, `alternative-id`, `subject`, and `title` are correctly converted to strings.
- **Enhanced Compatibility**: Added robust mapping for Crossref item types to standard CSL-JSON types (e.g., `journal-article` -> `article-journal`).
- **Data Cleanup**: Automatically strips problematic non-standard Crossref fields (`license`, `assertion`, `relation`, `updated-by`) that cause Pandoc parsing failures.
- **Cache Refresh Logic**: Updated the sync engine to automatically re-normalize all existing bibliography entries, ensuring that legacy cached data is always updated to the latest compatible format.

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
