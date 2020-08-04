from slackeventsapi import SlackEventAdapter
from slack import WebClient
from slack.errors import SlackApiError
from flask import abort, Flask, jsonify, request
from datetime import datetime, timedelta, timezone
from dateutil import relativedelta
from datetime import datetime
from dateutil.tz import tzutc, tzlocal
import os
import re


# Slack Event Adapter for receiving actions via the Events API
slack_signing_secret = os.environ["SLACK_SIGNING_SECRET"]
slack_events_adapter = SlackEventAdapter(slack_signing_secret, "/slack/events")

# Create a SlackClient for the bot to use for Web API requests
slack_bot_token = os.environ["SLACK_BOT_TOKEN"]
slack_user_token = os.environ["SLACK_OAUTH_TOKEN"]
slack_client = WebClient(slack_bot_token)

app = Flask(__name__)


def is_request_valid(request):
    is_token_valid = request.form['token'] == os.environ['SLACK_VERIFICATION_TOKEN']
    is_team_id_valid = request.form['team_id'] == os.environ['SLACK_TEAM_ID']

    return is_token_valid and is_team_id_valid


def access_logs():
    try:
        response = slack_client.team_accessLogs(token=slack_user_token)
        return response
    except SlackApiError as e:
        assert e.response["ok"] is False
        assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'
        error_handler(e)


def get_last_login(user_id, access_log):
    """
    Get last login for a Slack user.

    Parameters
    ----------
    user_id : str
    access_log : json

    Returns
    -------
    last_login : datetime
    """
    try:
        for login in access_log['logins']:
            if login['user_id'] == user_id:
                ts = (login['date_last'])
                last_login = datetime.utcfromtimestamp(ts)
                return last_login
    except Exception as e:
        error_handler(e)
    else:
        return None


def humanize_time(time):
    """
    Get a datetime object and return a relative time string like
    "one hour ago", "yesterday", "3 months ago", "just now", etc.
    """
    now = datetime.now(timezone.utc)
    naive = datetime.replace(now, tzinfo=None)
    rd = relativedelta.relativedelta(naive, time)

    def line(number, unit):
        if abs(number) < 10 and unit == "seconds":
            return "just now"
        if number == 1 and unit == "days":
            return 'yesterday'
        if number == -1 and unit == "days":
            return "tomorrow"

        prefix, suffix = '', ''
        unit = unit if abs(number) > 1 else unit[:-1]  # Unpluralizing.

        if number > 0:
            suffix = " ago"
        else:
            prefix = "in "

        return "%s%d %s%s" % (prefix, abs(number), unit, suffix)

    for attr in ['years', 'months', 'days', 'hours', 'minutes', 'seconds']:
        value = getattr(rd, attr)
        if value != 0:
            return line(value, attr)

    return "just now"


@app.route('/hello-there', methods=['POST'])
def hello_there():
    if not is_request_valid(request):
        abort(400)

    message = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "_*General Kenobi!*_"
            }
        },
        {
            "type": "image",
            "image_url": "https://external-content.duckduckgo.com/iu/?u=https%3A%2F%2Fi.ytimg.com%2Fvi%2FfrszEJb0aOo%2Fmaxresdefault.jpg&f=1&nofb=1",
            "alt_text": "General Grievous"
        }
    ]
    return jsonify(
        response_type='in_channel',
        text='General Kenobi!',
        blocks=message
    )


@app.route('/last-login', methods=['POST'])
def last_login():
    if not is_request_valid(request):
        abort(400)

    command_args = request.form['text']
    if not re.search("<@\w+\|\w+>", command_args):
        message = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Please enter a valid user."
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"Command ran: /last-login {command_args}"
                    }
                ]
            }
        ]
        return jsonify(
            response_type='ephemeral',
            text=f"Please enter a valid user.",
            blocks=message
        )
    user = re.search('<@(.*)\|\w+>', command_args).group(1)
    try:
        response = access_logs()
        if response is not None:
            last_login = get_last_login(user, response)
            if last_login is not None:
                time = humanize_time(last_login)
                message = [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": f"<@{user}> was last seen {time}."
                        }
                    },
                    {
                        "type": "divider"
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": f"Command ran: /last-login <@{user}>"
                            }
                        ]
                    }
                ]
                return jsonify(
                    response_type='ephemeral',
                    text=f"<@{user}> was last seen {time}.",
                    blocks=message
                )
        else:
            message = [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Could not get last login for <@{user}>."
                    }
                },
                {
                    "type": "divider"
                },
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"Command ran: /last-login <@{user}>"
                        }
                    ]
                }
            ]
            return jsonify(
                response_type='ephemeral',
                text=f"Could not get last login for <@{user}>.",
                blocks=message
            )
    except SlackApiError as e:
        assert e.response["ok"] is False
        assert e.response["error"]  # str like 'invalid_auth', 'channel_not_found'
        error_handler(e.response['error'])


# Error events
@slack_events_adapter.on("error")
def error_handler(err):
    print("ERROR: " + str(err))

# Once we have our event listeners configured, we can start the
# Flask server with the default `/events` endpoint on port 3000
# slack_events_adapter.start(port=3000)
