# Contributing to Smart Irrigation System

Thank you for your interest in contributing to the Smart Irrigation System! Your contributions help make this project better and more useful for everyone. This document outlines the guidelines and processes for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Contribute](#how-to-contribute)
  - [Reporting Bugs](#reporting-bugs)
  - [Suggesting Enhancements](#suggesting-enhancements)
  - [Submitting Pull Requests](#submitting-pull-requests)
- [Development Guidelines](#development-guidelines)
  - [Coding Standards](#coding-standards)
  - [Commit Messages](#commit-messages)
  - [Testing](#testing)
- [Questions and Help](#questions-and-help)

## Code of Conduct

This project adheres to the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/). By participating in this project, you are expected to uphold this code. Please report any unacceptable behavior to the project maintainers.

## How to Contribute

There are several ways you can contribute to the Smart Irrigation System:

### Reporting Bugs

- **Search First:** Before submitting a bug report, please search the issue tracker to see if the bug has already been reported.
- **Submit an Issue:** If you find a new bug, please create an issue with a clear and descriptive title and a detailed description of the problem. Include steps to reproduce the issue and any relevant logs or screenshots.

### Suggesting Enhancements

- **Feature Requests:** If you have ideas for new features or enhancements, please submit an issue with the "enhancement" tag. Provide as much detail as possible about your suggestion and its potential benefits.
- **Discussion:** For larger changes or ideas, feel free to start a discussion in the issue tracker before beginning any work.

### Submitting Pull Requests

1. **Fork the Repository:** Fork the repository to your own GitHub account.
2. **Create a Branch:** Create a new branch for your changes. Use a descriptive branch name, such as `feature/add-zone-validation` or `bugfix/fix-watering-calculation`.
3. **Make Changes:** Commit your changes following the development guidelines below.
4. **Run Tests:** Ensure all existing tests pass and add new tests as needed.
5. **Submit a Pull Request:** Submit a pull request to the main repository. Include a clear description of the changes, the motivation behind them, and any related issues.

## Development Guidelines

### Coding Standards

- **Language:** The project is primarily written in Python. Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) for Python code style.
- **Comments:** Write clear comments and docstrings for functions and classes.
- **Modularity:** Keep changes modular. If you're adding new features, try to design them in a way that does not disrupt existing functionality.

### Commit Messages

- **Format:** Use clear, concise commit messages. Follow the conventional commit format if possible:
  - **feat:** A new feature
  - **fix:** A bug fix
  - **docs:** Documentation changes
  - **style:** Code style changes (formatting, missing semicolons, etc.)
  - **refactor:** Code refactoring without adding new features or fixing bugs
  - **test:** Adding or updating tests

- **Example:**  

feat: add support for zone-specific moisture thresholds

This update allows users to configure individual moisture thresholds per zone, ensuring better control over irrigation for diverse garden areas.

### Testing

- **Write Tests:** All new features and bug fixes should be accompanied by relevant tests. The project uses integration tests to verify functionality.
- **Run Tests:** Make sure to run the entire test suite before submitting a pull request.
- **Test Coverage:** Contributions should strive to maintain or improve the current test coverage.

## Questions and Help

If you have any questions or need help, feel free to:
- Open an issue on the repository.
- Join the project discussions on GitHub.
- Reach out to the maintainers directly through GitHub.

Thank you for contributing to the Smart Irrigation System! Your efforts help improve the project and support a smarter, more sustainable way to manage irrigation.