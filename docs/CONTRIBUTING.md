# Contributing to Sports Fest ChMeetings Integration

Thank you for your interest in contributing to the Sports Fest ChMeetings Integration project! This document provides guidelines for contributing to both the Windows middleware and WordPress plugin components.

## Acknowledgement

The Sports Fest system was original created by Vu Phan in the late 90s on Microsoft Access 97. When that went away, Bumble recreated it using Podio.com and Globiflow with Jerry Phan's help. Since Podio.com has not been in active development, Bumble used ChMeetings.com for Registration and Profile Management and create this Python middleware integration with a frontend Wordpress system to make up for the missing operational components from Podio.

The system was brainstormed with ChatGPT 4o, architected and coded with Claude 3.7, and debugged by Grok 3 beta. Bumble was just a human driver and collaborator with them. Below this line are the contributing guidelines from Claude. It would be nice if we have more human contributors :-)

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Workflow](#development-workflow)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Documentation](#documentation)
- [Feature Requests](#feature-requests)
- [Bug Reports](#bug-reports)

## Code of Conduct

This project is maintained by the Vietnamese Alliance Youth Sports Ministry. As contributors and maintainers, we pledge to respect everyone who contributes by reporting issues, posting feature requests, updating documentation, submitting pull requests, and other activities.

We are committed to making participation in this project a harassment-free experience for everyone, regardless of age, body size, disability, ethnicity, gender identity and expression, level of experience, nationality, personal appearance, race, religion, or sexual identity and orientation.

Examples of unacceptable behavior include:

- Using sexualized language or imagery
- Personal attacks or derogatory comments
- Public or private harassment
- Publishing others' private information without permission
- Other conduct which could reasonably be considered inappropriate in a professional setting

Project maintainers have the right and responsibility to remove, edit, or reject comments, code, wiki edits, issues, and other contributions that are not aligned with this Code of Conduct.

## Getting Started

### Prerequisites

- Familiarity with Python (for middleware) or PHP/WordPress (for plugin)
- Git and GitHub account
- Development environment set up according to [INSTALLATION.md](INSTALLATION.md)

### Clone the Repository

```bash
git clone https://github.com/username/sports-fest-integration.git
cd sports-fest-integration
```

### Install Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # Development dependencies
```

## Development Workflow

1. **Create a branch** for your feature or bugfix:

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/your-bugfix-name
```

2. **Make your changes** to the code, tests, and documentation.

3. **Run tests** to ensure your changes don't break existing functionality:

```bash
pytest tests/
```

4. **Commit your changes** with clear, descriptive commit messages:

```bash
git commit -m "Add feature: description of your changes"
```

5. **Push your branch** to GitHub:

```bash
git push origin feature/your-feature-name
```

6. **Create a pull request** against the `main` branch.

## Pull Request Process

1. Update the README.md or documentation with details of changes if applicable.
2. Update the CHANGELOG.md with a description of your changes.
3. Include tests that verify your changes work as expected.
4. The PR will be merged once it receives approval from the project maintainers.

## Coding Standards

### Python (Middleware)

- Follow [PEP 8](https://www.python.org/dev/peps/pep-0008/) style guide
- Use type hints where appropriate
- Use docstrings for all functions, classes, and modules
- Maximum line length of 100 characters
- Use pylint and flake8 for code quality checks

Example:

```python
def process_data(input_data: dict) -> List[Dict]:
    """
    Process the input data and return a list of processed records.
    
    Args:
        input_data: Dictionary containing raw data
        
    Returns:
        List of processed data dictionaries
    """
    # Implementation here
```

### PHP (WordPress Plugin)

- Follow [WordPress Coding Standards](https://developer.wordpress.org/coding-standards/wordpress-coding-standards/php/)
- Use proper indentation (4 spaces)
- Use meaningful function and variable names
- Add PHPDoc comments for functions and classes
- Prefix all functions, classes, and global variables with `vaysf_`

Example:

```php
/**
 * Get participant data by ID.
 *
 * @param int $participant_id Participant ID.
 * @return array|false Participant data or false if not found.
 */
function vaysf_get_participant($participant_id) {
    global $wpdb;
    
    $table_name = vaysf_get_table_name('participants');
    
    return $wpdb->get_row(
        $wpdb->prepare("SELECT * FROM $table_name WHERE participant_id = %d", $participant_id),
        ARRAY_A
    );
}
```

## Testing

### Python (Middleware)

- Write tests using pytest
- Tests should be in the `tests/` directory
- Test files should be named `test_*.py`
- Include both unit tests and integration tests
- Use mock objects for external dependencies
- Test with both mock mode and live mode (with appropriate env var)

Example:

```python
def test_sync_churches(sync_manager, mocker):
    """Test syncing churches from Excel to WordPress."""
    # Arrange
    mocker.patch.object(sync_manager.wordpress_connector, "create_church", return_value={"church_id": 1})
    
    # Act
    result = sync_manager.sync_churches_from_excel("test_data.xlsx")
    
    # Assert
    assert result is True
    assert sync_manager.stats["churches"]["created"] > 0
```

### PHP (WordPress Plugin)

- Write unit tests using PHPUnit
- Test REST API endpoints
- Include WordPress-specific tests for hooks and filters
- Test database operations

## Documentation

- Update README.md with any new features
- Add or update comments in the code
- Update function docstrings and parameter descriptions
- Keep the documentation in the docs/ directory up to date
- Add examples for new features

## Feature Requests

Feature requests are welcome! Please create an issue on GitHub with:

1. A clear title and description
2. As much relevant information as possible
3. A specific use case

## Bug Reports

When reporting bugs, please include:

1. Your operating system and version
2. Python version and key package versions
3. WordPress version and plugin version
4. Detailed steps to reproduce the bug
5. What you expected would happen
6. What actually happened
7. Relevant logs or screenshots

---

Thank you for contributing to the Sports Fest ChMeetings Integration project!
