#!/usr/bin/env python3
#===============================================================================
#
# Script Name: replstatus.py
# Title: MySQL replication status
# Tags: Replication, Monitoring
# Purpose: Compare primary and standby binary log positions and email the result
#
# Description:
#   Connects with login-path primary and standby, reads log_status and
#   slave_relay_log_info, then sends an HTML status email.
#
# Parameters:
#   None.
#
# Required Privileges:
#   - mysql login-path primary and standby
#   - SELECT on performance_schema.log_status
#   - SELECT on mysql.slave_relay_log_info
#   - SMTP access to smtp.gmail.com
#
# Output Format:
#   - HTML email with host, binary log, position, and sync status
#
# Example Usage:
#   python replstatus.py
#
# Author: Aaron Myers <aaron@balddba.com>
#
#===============================================================================
import json
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import myloginpath
import mysql.connector

def sync_status(primary_log: str, primary_pos: int, standby_log: str, standby_pos: int) -> str:
    """
    Determines the synchronization status between primary and standby databases.

    Args:
        primary_log (str): The binary log file name of the primary database.
        primary_pos (int): The binary log position of the primary database.
        standby_log (str): The binary log file name of the standby database.
        standby_pos (int): The binary log position of the standby database.

    Returns:
        str: An HTML string indicating the synchronization status with a color-coded message.
    """
    # Extract the numeric part of the log file names for comparison
    primary_log_number: int = int(primary_log.split(".")[1])
    standby_log_number: int = int(standby_log.split(".")[1])

    # Define status messages for different synchronization scenarios
    status_messages = {
        (True, True): '<div style="color: green;">Databases are in sync</div>',
        (True, False): '<div style="color: blue;">Binary logs are in sync, log positions are not.</div>',
        (False, True): '<div style="color: yellow;">Binlogs are off by 1 log, this could just be the standby lagging</div>',
        (False, False): '<div style="color: red;">Databases are out of sync</div>'
    }

    # Determine if logs and positions are in sync
    logs_in_sync = primary_log_number == standby_log_number
    positions_in_sync = primary_pos == standby_pos or (primary_log_number != standby_log_number and primary_pos - standby_pos < 2)

    # Return the appropriate status message based on the sync conditions
    return status_messages[(logs_in_sync, positions_in_sync)]

def main():
    """
    Main function to check the synchronization status between primary and standby databases
    and send an email notification with the status details.

    This function connects to both primary and standby databases to retrieve binary log
    information, constructs an HTML email body with the synchronization status, and sends
    the email to specified recipients.
    """
    debugging: bool = False
    # Parse database connection configurations for primary and standby databases
    primary_conf: dict[str, str] = myloginpath.parse("primary")
    standby_conf: dict[str, str] = myloginpath.parse("standby")

    # Connect to the primary database and retrieve binary log information
    primary = mysql.connector.connect(**primary_conf)
    c = primary.cursor()
    c.execute("select local from performance_schema.log_status")
    # {"gtid_executed": "849d8d3f-9496-11e6-94a5-0050569e2335:1-294615096,\nc6881cf4-5ba6-11ee-8db9-0050569eba7b:1-1156346", "binary_log_file": "binlog.000019", "binary_log_position": 82839086}
    data = json.loads(c.fetchone()[0])
    primary_bin_log = data["binary_log_file"]
    primary_bin_log_position = data["binary_log_position"]
    c.close()

    # Connect to the standby database and retrieve binary log information
    standby = mysql.connector.connect(**standby_conf)
    c = standby.cursor()
    c.execute("select Master_log_name, Master_log_pos from mysql.slave_relay_log_info")
    (standby_bin_log_b, standby_bin_log_position) = c.fetchone()
    standby_bin_log = str(standby_bin_log_b)
    c.close()


    # Construct the HTML email body with synchronization status details
    email_body: str = f"""
        <html>
          <body style="font-family: Arial, sans-serif; background-color: #f4f4f4; margin: 0; padding: 20px;">
            <table style="width: 100%; max-width: 800px; margin: auto; background-color: #ffffff; border-collapse: collapse; box-shadow: 0 0 10px rgba(0, 0, 0, 0.1);">
              <tr style="background-color: #0073e6; color: #ffffff;">
                <td style="padding: 10px; white-space: nowrap;"></td>
                <td style="padding: 10px; white-space: nowrap;"><u><b>Primary</b></u></td>
                <td style="padding: 10px; white-space: nowrap;"><u><b>Standby</b></u></td>
              </tr>
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;"><b>Hostname</b></td>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{primary_conf["host"]}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{standby_conf["host"]}</td>
              </tr>
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;"><b>Binary Log:</b></td>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{primary_bin_log}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{standby_bin_log}</td>
              </tr>
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;"><b>Log Position:</b></td>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{primary_bin_log_position}</td>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{standby_bin_log_position}</td>
              </tr>
              <tr>
                <td style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;"><b>Sync Status:</b></td>
                <td colspan="2" style="padding: 10px; border-bottom: 1px solid #dddddd; white-space: nowrap;">{sync_status(primary_bin_log, primary_bin_log_position, standby_bin_log, standby_bin_log_position)}</td>
              </tr>
              <tr>
                <td style="padding: 10px; white-space: nowrap;"><b>Run Time:</b></td>
                <td colspan="2" style="padding: 10px; white-space: nowrap;">{datetime.now()}</td>
              </tr>
            </table>
          </body>
        </html>
    """

    # Define email recipients and sender
    if debugging:
        to_list: list[str] = ["aaron@balddba.com"]
    else:
        to_list = ["aaron@balddba.com"]
    to_str: str = ", ".join(to_list)
    from_address: str = "aaron@balddba.com"

    # Create the email message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Redcap Replication Status"
    msg["From"] = to_str
    msg["To"] = from_address

    # Attach the HTML body to the email
    msg_html_body = MIMEText(email_body, "html")
    msg.attach(msg_html_body)

    # Send the email using SMTP
    with smtplib.SMTP("smtp.gmail.com") as s:
        s.sendmail(from_addr=from_address, to_addrs=to_list, msg=msg.as_string())

if __name__ == "__main__":
    # execute only if run as a script
    main()