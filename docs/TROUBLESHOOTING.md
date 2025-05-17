# Troubleshooting Guide

This guide addresses common issues you might encounter when using the Sports Fest ChMeetings Integration system and provides solutions to resolve them.

## Table of Contents

- [Windows Middleware Issues](#windows-middleware-issues)
- [WordPress Plugin Issues](#wordpress-plugin-issues)
- [ChMeetings Integration Issues](#chmeetings-integration-issues)
- [Data Synchronization Issues](#data-synchronization-issues)
- [Email Delivery Issues](#email-delivery-issues)
- [Performance Issues](#performance-issues)

## Windows Middleware Issues

### Connection Errors

**Issue**: The middleware can't connect to ChMeetings or WordPress.

**Solutions**:
1. Verify API credentials in `.env` file
2. Check network connectivity
3. Ensure API endpoints are accessible
4. Run the connectivity test:
   ```bash
   python main.py test --system all --test-type connectivity
   ```
5. If the config is still failing, run `python main.py config --validate` to check for any missing or misconfigured environment variables

### Python Dependency Errors

**Issue**: Package import errors or dependency issues.

**Solutions**:
1. Ensure all dependencies are installed:
   ```bash
   pip install -r requirements.txt
   ```
2. Check for Python version compatibility (3.8+ required)
3. If using a virtual environment, make sure it's activated:
   ```bash
   venv\Scripts\activate
   ```

### Selenium WebDriver Issues

**Issue**: Selenium operations fail or Chrome crashes.

**Solutions**:
1. Ensure Chrome and ChromeDriver versions match
2. Update ChromeDriver to latest version
3. Try running Chrome in non-headless mode for debugging:
   ```
   # In .env file
   USE_CHROME_HEADLESS=False
   ```
4. Check Chrome profile path if using a custom profile

### Excel File Errors

**Issue**: Church sync fails with Excel-related errors.

**Solutions**:
1. Verify Excel file path is correct
2. Check Excel file format (should be .xlsx)
3. Ensure required columns are present
4. Open Excel file manually to check for corruption
5. Save Excel file in compatibility mode if using a newer version

## WordPress Plugin Issues

### Database Table Creation Failure

**Issue**: WordPress plugin activated but tables not created.

**Solutions**:
1. Deactivate and reactivate the plugin
2. Check WordPress database user permissions
3. Look for errors in WordPress debug log
4. Manually run the SQL from `vaysf.php`

### API Authentication Errors

**Issue**: Middleware can't authenticate with WordPress API.

**Solutions**:
1. Verify API key in WordPress settings and middleware `.env`
2. Ensure WordPress site is using HTTPS
3. Check WordPress server has proper SSL configuration
4. Temporarily disable security plugins that might block API access

### REST API Errors

**Issue**: REST API endpoints return errors or unexpected responses.

**Solutions**:
1. Check WordPress error logs
2. Ensure permalink structure is set correctly (Post name)
3. Verify WordPress version is compatible (5.8+)
4. Try accessing endpoints directly in browser to see error details

## ChMeetings Integration Issues

### API Authentication Failures

**Issue**: Middleware can't authenticate with ChMeetings API.

**Solutions**:
1. Verify API credentials in `.env` file
2. Check if ChMeetings API key has expired
3. Contact ChMeetings support to verify API access
4. Check for account restrictions or rate limits

### Data Mapping Problems

**Issue**: ChMeetings data not mapping correctly to WordPress fields.

**Solutions**:
1. Check ChMeetings form field names match expected values
2. Verify additional fields are set up correctly in ChMeetings
3. Examine raw data using the middleware debug function:
   ```python
   logger.debug(f"Raw person_data for {person_id}: {person_data}")
   ```

### Group Access Issues

**Issue**: Middleware can't access ChMeetings groups.

**Solutions**:
1. Verify user account has permissions to access groups
2. Check if groups are properly set up with "Team" prefix
3. Ensure group IDs are correct
4. Check for changes in ChMeetings API structure

### Participants Not Assigned to Groups

**Issue**: Participants have a church code but are not in any "Team [Code]" group in ChMeetings, causing potential omissions in group-based lists.

**Solutions**:
1. Ensure that all church teams exist as groups in ChMeetings (e.g., "Team ABC")
2. Ensure that the Participant Individual Form's "Church Team" has "ABC"
3. Run the `assign-groups` command to generate a list of unassigned individuals:
   ```bash
   python main.py assign-groups
   ```
   Then import the generated file into ChMeetings to assign those people to their groups
4. Verify that your ChMeetings Church Rep user has permission to manage groups (lack of permission could prevent them from reading group memberships)

## Data Synchronization Issues

### Missing Participants

**Issue**: Some participants don't sync from ChMeetings to WordPress.

**Solutions**:
1. Check if participants have the "Athlete/Participant" role
2. Verify participants are in the correct ChMeetings groups
3. Check for validation errors in the middleware log
4. Look for duplicate ChMeetings IDs
5. If a specific participant is not syncing, try syncing just that individual by ID:
   ```bash
   python main.py sync --type participants --chm-id <Their_ChMeetings_ID>
   ```
   This can reveal if there's a data issue with that record alone, especially with a specific Debug Target ID (added in v1.02 for `participants.py`). This direct approach can help debug one participant's data without running a full sync.

### Roster Creation Failures

**Issue**: Sport rosters not being created correctly.

**Solutions**:
1. Check participant sport fields are filled correctly
2. Verify sport format mappings in `config.py`
3. Look for validation issues related to sports
4. Manually create test roster entries in WordPress admin
5. Check logs for roster-specific errors

### Validation Issues Not Detected

**Issue**: Validation rules not catching eligibility problems.

**Solutions**:
1. Verify JSON validation rules are correct
2. Check for missing or misconfigured rules
3. Ensure rules match the current Sports Fest requirements
4. Test with known invalid data to confirm rules work
5. Run a manual validation check:
   ```bash
   python main.py sync --type validation
   ```

## Email Delivery Issues

### Pastor Approval Emails Not Sent

**Issue**: Pastors not receiving approval emails.

**Solutions**:
1. Check WordPress email configuration
2. Install and configure WP Mail SMTP plugin
3. Verify pastor email addresses are correct
4. Check for emails in spam folders
5. Test email delivery:
   ```bash
   python main.py test --system wordpress --test-type email --test-email "test@example.com"
   ```

### Approval Links Not Working

**Issue**: Approval links in emails don't work correctly.

**Solutions**:
1. Check WordPress site URL configuration
2. Verify approval tokens are being generated correctly
3. Ensure token expiry dates are set properly
4. Check pastor-approval.php template for errors
5. Test approval process manually in WordPress admin

## Performance Issues

### Slow Synchronization

**Issue**: Sync operations take too long to complete.

**Solutions**:
1. Increase batch size in config.py:
   ```python
   BATCH_SIZE = 100  # Default is 50
   ```
2. Ensure database indexes are optimized
3. Run targeted syncs instead of full syncs:
   ```bash
   # Sync one participant
   python main.py sync --type participants --chm-id 1234567

   # How about syncing one church ?
   ```
4. Schedule syncs during low-traffic periods
5. Update logging level to reduce I/O:
   ```
   # In .env file
   DEBUG=False
   ```

### Memory Usage Problems

**Issue**: Middleware consumes excessive memory.

**Solutions**:
1. Process large datasets in smaller batches
2. Clean up resources properly after operations
3. Check for memory leaks (objects not being garbage collected)
4. Restart middleware more frequently
5. Consider increasing system memory if needed

### WordPress Admin Interface Slow

**Issue**: WordPress admin pages load slowly.

**Solutions**:
1. Optimize WordPress database
2. Use pagination for large data sets
3. Install WordPress caching plugin
4. Check server resources
5. Consider upgrading WordPress hosting

## Advanced Troubleshooting

For more complex issues, the following techniques can help identify the source of problems:

### Error Log Analysis

Check the logs in the `logs` directory for detailed error information. The logging level can be adjusted in `config.py`:

```python
# In config.py
logger.add(log_file, rotation="1 day", retention="30 days", level="DEBUG")
```

### Database Inspection

Directly inspect the WordPress database tables to check for data issues:

```sql
-- Check participants table
SELECT * FROM wp_sf_participants WHERE approval_status = 'pending';

-- Check validation issues
SELECT * FROM wp_sf_validation_issues WHERE status = 'open';

-- Check for orphaned roster entries
SELECT r.* FROM wp_sf_rosters r
LEFT JOIN wp_sf_participants p ON r.participant_id = p.participant_id
WHERE p.participant_id IS NULL;
```

### API Request Monitoring

Use browser developer tools or tools like Postman to monitor API requests and responses:

1. Open browser developer tools (F12)
2. Go to Network tab
3. Filter for API requests to the WordPress site
4. Examine request/response headers and body

### Test Environment

Create a separate test environment to isolate issues:

1. Clone the WordPress site to a test domain
2. Set up a test ChMeetings environment
3. Configure middleware to use test endpoints
4. Run tests without affecting production data