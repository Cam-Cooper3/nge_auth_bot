# Discord Bot: NGE Authenticator

## Table of Contents

1. [Introduction](#introduction)
2. [Features](#features)
3. [Installation and Setup](#installation-and-setup)
4. [Commands](#commands)
5. [Technical Details](#technical-details)
6. [Contributing](#contributing)
7. [License](#license)

## Introduction

The **NGE Authenticator** is a Discord bot designed to streamline user compliance and management within our NG Esports server. It leverages the Discord API and SQLite to verify and maintain members' profile details, ensuring that all users meet specific server requirements, such as proper nicknames and unique identifiers.

## Features

- **User Compliance Enforcement:**
  - Ensures members have compliant nicknames (FirstName LastName format).
  - Verifies members have a unique identifier (MyID) stored in the database.
- **Role Management:**
  - Automatically assigns or removes roles based on compliance.
  - Sends notifications to server owners and members about required updates.
- **Commands:**
  - Scan all members or specific members for compliance.
  - Add, retrieve, or list MyIDs for members.
  - Wipe all stored MyIDs from the database.
- **Server-Wide Notifications:**
  - Notifies the server owner if the bot’s role is not at the top of the role hierarchy.

## Installation and Setup

### Prerequisites

1. Python 3.8 or higher
2. Discord Developer Account
3. SQLite (bundled with Python by default)

### Setup Instructions

1. Clone this repository:

   ```bash
   git clone <repository_url>
   cd <repository_folder>
   ```

2. Create a `.env` file with the following content:

   ```env
   DISCORD_BOT_TOKEN=<Your_Discord_Bot_Token>
   DISCORD_SERVER_ID=<Your_Server_ID>
   ```

   Replace `<Your_Discord_Bot_Token>` with your bot token and `<Your_Server_ID>` with your server's ID.

3. Run the bot:

   ```bash
   python main.py
   ```

> [!NOTE]
> - Ensure the bot’s role in your server has the appropriate permissions, including the ability to manage roles and nicknames.
> - Place the bot’s role at the top of the role hierarchy for proper functionality.

## Commands

### Admin Commands

1. **`/scan_server`**

   - Scans all server members for compliance.
   - Outputs the number of compliant and non-compliant members.

2. **`/scan_member @member`**

   - Scans a specific member for compliance.
   - Notifies the member if they are non-compliant.

3. **`/add_myid @member MyID`**

   - Adds or updates the MyID for a specific member.
   - If no member is mentioned, adds/updates the invoking user’s MyID.

4. **`/get_myid @member`**

   - Retrieves the MyID of a specific member.

5. **`/list_myids`**

   - Lists all stored MyIDs in the database.

6. **`/wipe_myids`**

   - Deletes all stored MyIDs from the database. Requires confirmation.

## Technical Details

### File Overview

1. **`main.py`**: The main bot script, handles all events, commands, and database interactions.
2. **`.env`**: Stores environment variables, including bot token and server ID.
3. **`.myids.db`**: SQLite database file to store user data (First Name, Last Name, and MyID).

### Key Functionalities

- **Event Handling:**
  - `on_ready`: Ensures proper initialization and syncs slash commands with the server.
  - `on_member_update`: Checks member updates for compliance.
- **Database Management:**
  - SQLite database stores user data and ensures uniqueness of MyIDs.
  - Auto-creates necessary tables if they do not exist.
- **Role Enforcement:**
  - Ensures members have the required roles and compliant nicknames.
  - Transfers non-compliant users to the general role and notifies them via DM.

## License

This project is licensed under the MIT License. See the LICENSE file for details.

