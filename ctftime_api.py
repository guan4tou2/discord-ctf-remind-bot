"""
CTFtime API client for fetching competition and team information.
This module provides a clean interface to interact with CTFtime's API and web scraping endpoints.
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

# Configure logging
logger = logging.getLogger(__name__)

# Constants
BASE_URL = "https://ctftime.org"
API_BASE_URL = f"{BASE_URL}/api/v1"
DEFAULT_TIMEOUT = 30
DEFAULT_RETRIES = 3

# Custom headers to avoid rate limiting
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}


class CTFtimeError(Exception):
    """Base exception for CTFtime API errors."""

    pass


class CTFtimeAPIError(CTFtimeError):
    """Raised when there's an error with the CTFtime API."""

    pass


class CTFtimeConnectionError(CTFtimeError):
    """Raised when there's a connection error with CTFtime."""

    pass


class CTFtimeParseError(CTFtimeError):
    """Raised when there's an error parsing CTFtime data."""

    pass


def _make_request(
    url: str, timeout: int = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES
) -> requests.Response:
    """Make a request to CTFtime with retry logic.

    Args:
        url: The URL to request
        timeout: Request timeout in seconds
        retries: Number of times to retry failed requests

    Returns:
        Response object from requests

    Raises:
        CTFtimeConnectionError: If connection fails after all retries
        CTFtimeAPIError: If API returns an error response
    """
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=timeout)
            response.raise_for_status()
            return response
        except requests.Timeout:
            if attempt == retries - 1:
                raise CTFtimeConnectionError("Connection to CTFtime timed out")
            continue
        except requests.RequestException as e:
            if attempt == retries - 1:
                raise CTFtimeConnectionError(f"Failed to connect to CTFtime: {str(e)}")
            continue


def get_event(event_id: str) -> Optional[Dict]:
    """Get detailed information about a specific CTF event.

    Args:
        event_id: The CTFtime event ID

    Returns:
        Dict containing event information or None if not found

    Raises:
        CTFtimeError: If there's any error fetching or parsing the event
    """
    try:
        response = _make_request(f"{API_BASE_URL}/events/{event_id}/")
        event = response.json()

        # Parse start and end times
        start_time = event.get("start")
        end_time = event.get("finish")

        if not (start_time and end_time):
            logger.warning(f"Event {event_id} missing start or end time")
            return None

        # Convert to ISO format with timezone
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

        return {
            "title": event.get("title", "Unknown"),
            "description": event.get("description", "No description available"),
            "start": start_dt.isoformat(),
            "finish": end_dt.isoformat(),
            "url": event.get("url", ""),
            "ctftime_url": event.get("ctftime_url", f"{BASE_URL}/event/{event_id}"),
            "format": event.get("format", "Unknown"),
            "weight": float(event.get("weight", 0)),
            "location": event.get("location", "Online"),
            "id": event_id,
        }

    except (CTFtimeError, ValueError, KeyError) as e:
        logger.error(f"Error getting event {event_id}: {str(e)}")
        return None


def get_team_events(team_id: str) -> List[Dict]:
    """Get a list of events that a team is planning to participate in.

    Args:
        team_id: The CTFtime team ID

    Returns:
        List of dicts containing event information

    Raises:
        CTFtimeError: If there's any error fetching or parsing team events
    """
    try:
        response = _make_request(f"{BASE_URL}/team/{team_id}")
        soup = BeautifulSoup(response.text, "html.parser")

        events = []
        table = soup.find("table")
        if not table:
            logger.warning(f"No events table found for team {team_id}")
            return events

        for row in table.find_all("tr")[1:]:  # Skip header row
            cols = row.find_all("td")
            if len(cols) < 2:
                continue

            event_link = cols[0].find("a")
            if not event_link:
                continue

            event_name = event_link.text.strip()
            event_url = event_link["href"]
            event_id = event_url.split("/")[-1]
            event_date = cols[1].text.strip()

            events.append(
                {
                    "name": event_name,
                    "date": event_date,
                    "url": f"{BASE_URL}{event_url}",
                    "id": event_id,
                }
            )

        return events

    except CTFtimeError as e:
        logger.error(f"Error getting team events for team {team_id}: {str(e)}")
        return []


def get_upcoming_events(limit: int = 100) -> List[Dict]:
    """Get a list of upcoming CTF events.

    Args:
        limit: Maximum number of events to return

    Returns:
        List of dicts containing event information

    Raises:
        CTFtimeError: If there's any error fetching or parsing events
    """
    try:
        response = _make_request(f"{API_BASE_URL}/events/")
        events = response.json()
        return events[:limit]
    except CTFtimeError as e:
        logger.error(f"Error getting upcoming events: {str(e)}")
        return []
