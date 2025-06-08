# EmailVerify Redbot Cog

This cog provides email verification for users using Discord Modals and Buttons. Admins can manage verification status, blacklists, and configure the verified role.

## Features

- Users verify via email and receive a 6-digit code
- Modals used for email and code input
- Verified users get a specific role
- Admins can:
  - View all verifications
  - Blacklist or remove users
  - Set the global verified role
- Automatically unverifies users if they leave or are banned

## Setup

1. Load the cog:
   ```
   [p]load emailverify
   ```

2. Set the verified role:
   ```
   [p]verifyadmin setrole <role_id>
   ```

3. Send the button:
   ```
   [p]verifybutton
   ```

## Dependencies

- Redbot 3.5+
- `aiosqlite` (comes with Redbot)
- SMTP email configuration

Edit `send_email()` in the code to use your own SMTP server and credentials.
