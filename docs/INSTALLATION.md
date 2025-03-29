# Installation Guide

This guide provides step-by-step instructions for setting up the Sports Fest ChMeetings Integration system, including the middleware on Windows and the WordPress plugin.

## Prerequisites

### Windows Middleware Requirements

- Windows 10 or Windows 11
- Python 3.8 or higher
- Administrator privileges (for initial setup)
- Internet connection
- Microsoft Excel (for viewing and managing Excel files)
- Chrome browser (for Selenium operations if needed)

### WordPress Requirements

- WordPress 5.8+
- PHP 7.4+
- MySQL 5.7+ or MariaDB 10.4+
- WP Mail SMTP plugin (recommended for reliable email delivery)
- SSH or FTP access to your WordPress installation

### ChMeetings Requirements

- ChMeetings account with API access
- API key for accessing ChMeetings data

## Windows Middleware Setup

### 1. Install Python

1. Download Python 3.8+ from [python.org](https://www.python.org/downloads/windows/)
2. Run the installer, checking "Add Python to PATH"
3. Verify installation by opening Command Prompt and typing:
   ```
   python --version
   ```

### 2. Clone or Download the Repository

```bash
# Clone using Git
git clone https://github.com/username/sports-fest-integration.git

# Or download and extract the ZIP file from GitHub
```

### 3. Install Dependencies

```bash
# Navigate to the project directory
cd sports-fest-integration

# Create a virtual environment (optional but recommended)
python -m venv venv
venv\Scripts\activate

# Install required packages
pip install -r requirements.txt
```

### 4. Configure Environment Variables

1. Copy the template environment file:
   ```
   copy .env.template .env
   ```

2. Edit the `.env` file with your credentials:
   ```
   # ChMeetings configuration
   CHM_API_URL=https://api.chmeetings.com
   CHM_USERNAME=your_username
   CHM_PASSWORD=your_password
   CHM_API_KEY=your_api_key

   # WordPress configuration
   WP_URL=https://your-wordpress-site.com
   WP_API_KEY=your_wp_api_key

   # Email configuration
   EMAIL_FROM=sportsfest@example.com

   # Application settings
   APP_ENV=production
   DEBUG=False
   TOKEN_EXPIRY_DAYS=7
   CHURCH_EXCEL_FILE=Church Application Form.xlsx
   ```

### 5. Set Up Chrome for Selenium (Optional)

If you plan to use Selenium for ChMeetings operations:

1. Download Chrome WebDriver matching your Chrome version from [ChromeDriver](https://sites.google.com/chromium.org/driver/)
2. Place the executable in the project directory or specify its path in the `.env` file:
   ```
   CHROME_DRIVER_PATH=C:\path\to\chromedriver.exe
   ```

### 6. Verify Installation

Run a basic test to ensure everything is set up correctly:

```bash
python main.py test --system all --test-type connectivity
```

## WordPress Plugin Installation

### 1. Install the Plugin

1. Download the `vaysf.zip` plugin file
2. Log in to your WordPress admin dashboard
3. Navigate to Plugins > Add New > Upload Plugin
4. Choose the downloaded zip file and click "Install Now"
5. After installation completes, click "Activate Plugin"

### 2. Configure Plugin Settings

1. In WordPress admin, navigate to Sports Fest > Settings
2. Configure the following settings:
   - Token Expiry Days: Number of days before approval tokens expire
   - From Email: Email address used for sending approval emails
   - Approval Email Subject: Subject line for pastor approval emails
   - API Key: Generate a secure API key to allow middleware access

### 3. Set Up Database Tables

The plugin will automatically create the required database tables when activated. If you encounter any issues:

1. Deactivate and reactivate the plugin
2. Check the WordPress error log for any database-related errors

### 4. Configure Email Sending

For reliable email delivery, we recommend installing the WP Mail SMTP plugin:

1. Install and activate WP Mail SMTP
2. Configure it with your SMTP server details
3. Send a test email to verify it's working correctly

## Troubleshooting Installation

### Common Windows Middleware Issues

1. **Python Path Issues**
   - Ensure Python is added to PATH
   - Try using full paths to Python executables

2. **Package Installation Failures**
   - Try upgrading pip: `python -m pip install --upgrade pip`
   - Install Visual C++ Build Tools if required for some packages

3. **Selenium WebDriver Issues**
   - Ensure Chrome and ChromeDriver versions match
   - Try running Chrome in non-headless mode for debugging

### Common WordPress Plugin Issues

1. **Database Table Creation Failures**
   - Check WordPress database permissions
   - Manually run the SQL from `vaysf.php` if needed

2. **Email Delivery Problems**
   - Install WP Mail SMTP plugin
   - Check server's email configuration

For more troubleshooting help, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Next Steps

After installation is complete, proceed to the [Usage Guide](USAGE.md) to learn how to use the system effectively.
