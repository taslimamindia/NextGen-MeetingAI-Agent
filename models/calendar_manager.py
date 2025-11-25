from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from models.authentication import Authenticator
from zoneinfo import ZoneInfo


class CalendarManager(Authenticator):
    """Manager for Google Calendar operations."""

    def __init__(
        self,
        client_secrets_file: str = 'client_secrets.json',
        token_file: str = 'token.json',
        scopes: Optional[List[str]] = None,
        calendar_id: str = 'primary',
    ) -> None:
        # Do not set scopes here; Authenticator provides the application-wide defaults.
        super().__init__(client_secrets_file=client_secrets_file, token_file=token_file, scopes=scopes)
        self.service = self.build_service('calendar', 'v3')
        self.calendar_id = calendar_id
        self.zone = ZoneInfo("America/Toronto")
        self.start_hour = 9
        self.end_hour = 18

    def _to_local(self, dt: datetime) -> datetime:
        if dt.tzinfo is None:
            return dt.replace(tzinfo=self.zone)
        return dt.astimezone(self.zone)
    
    def _parse_rfc3339(self, value: str) -> datetime:
        if value.endswith("Z"):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(value)
        return dt.astimezone(self.zone)

    def _compute_free_slots(self, available_days, busy_slots, buffer_minutes=30):
        new_busy_slots = [
            {"start": slot["start"] - timedelta(minutes=buffer_minutes), "end": slot["end"] + timedelta(minutes=buffer_minutes)} 
            for slot in busy_slots
        ]

        free_slots = []
        for day in available_days:
            day_start = day["start"]
            day_end = day["end"]
            busy_for_day = [
                {
                    "start": max(slot["start"], day_start),
                    "end": min(slot["end"], day_end)
                }
                for slot in new_busy_slots
                if slot["start"].date() == day_start.date()
            ]
            busy_for_day.sort(key=lambda x: x["start"])

            current = day_start
            for slot in busy_for_day:
                if current < slot["start"]:
                    free_slots.append({"start": current, "end": slot["start"]})
                current = max(current, slot["end"])

            if current < day_end:
                free_slots.append({"start": current, "end": day_end})

        return free_slots

    def _format_date(self, dt: datetime) -> str:
        """Format datetime to a readable string."""
        return dt.strftime("%Y-%m-%d %H:%M:%S %z")

    def _format_slots_to_str(self, slots: List[Dict[str, datetime]]) -> List[Dict[str, str]]:
        """Format list of slots with datetime to strings."""
        return [
            {
                'start': self._format_date(slot['start']),
                'end': self._format_date(slot['end'])
            }
            for slot in slots
        ]

    def _check_valid_date_and_hour_range(self, date_to_check: datetime) -> datetime:
        """Ensure the specific date is within valid hours (9 AM to 6 PM)."""

        if date_to_check.hour < self.start_hour:
            date_to_check = date_to_check.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        elif date_to_check.hour > self.end_hour:
            date_to_check = date_to_check.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        
        return date_to_check

    def _get_day_range(self, specific_date: datetime) -> List[datetime] | str:
        """Get start and end datetime for a specific date."""
        try:
            specific_date_rfc = specific_date.replace(tzinfo=self.zone)
            tz = specific_date_rfc.tzinfo or self.zone
            start_s = datetime.combine(specific_date_rfc.date(), datetime.min.time(), tz)
            end_e = start_s + timedelta(days=1)
            
            return [start_s, end_e]
        except Exception as e:
            return f"An error occurred while processing the date: {e}"

    def _list_available_events(self, time_min: datetime, time_max: datetime = None) -> List[Dict[str, Any]] | str:
        """Return events whose title contains 'available' between two datetimes."""
        
        try:

            start_time = self._to_local(self._check_valid_date_and_hour_range(time_min))
            end_time_input = time_max if time_max else time_min
            end_time = self._to_local(self._check_valid_date_and_hour_range(end_time_input))
            end_temp = datetime.combine(end_time.date(), datetime.min.time(), self.zone) + timedelta(days=1)

            busy_resp = self.service.freebusy().query(
            body={
                "timeMin": start_time.isoformat(),
                "timeMax": end_temp.isoformat(),
                "items": [{"id": self.calendar_id}]
            }
            ).execute()

            raw_busy = (busy_resp.get("calendars", {})
                       .get(self.calendar_id, {})
                       .get("busy", []))

            busy_times = []
            for bt in raw_busy:
                rs = bt.get("start")
                re = bt.get("end")
                if not rs or not re:
                    continue
                bt_start = self._parse_rfc3339(rs)
                bt_end = self._parse_rfc3339(re)
                busy_times.append({
                    "start": bt_start,
                    "end": bt_end
                })
            
            s = start_time.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
            e = start_time.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
            available_times = [
                {
                    'start': s + timedelta(days=i), 
                    'end': e + timedelta(days=i)
                } 
                for i in range((end_time - start_time).days + 1)
            ]
            available_times[0]['start'] = start_time
            available_times[-1]['end'] = end_time
            available_times = self._compute_free_slots(available_times, busy_slots=busy_times)

            if len(available_times) > 2:
                available_times = [
                    slot for slot in available_times
                    if (slot["end"] - slot["start"]) >= timedelta(hours=1)
                ]
            
            available_times = [slot for slot in available_times if slot["start"].weekday() < 5]

            return available_times
        except Exception as e:
            raise RuntimeError(f"An error occurred while processing the date range: {e}")
       
    def _find_available_slots_after_date(self, specific_date: datetime, number_of_days: int = 7) -> List[Dict[str, str]] | str:
        """Return events on a specific date.
        
        Args:
            specific_date: The specific datetime to check for available slots.
        """

        try:
            start_of_day = self._check_valid_date_and_hour_range(specific_date)
            end_candidate = start_of_day
            business_days = 0
            while business_days < number_of_days:
                end_candidate = end_candidate + timedelta(days=1)
                if end_candidate.weekday() < 5:
                    business_days += 1
            end_of_day = end_candidate.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
            slots = self._list_available_events(start_of_day, end_of_day)
            if slots != []:
                slots = self._format_slots_to_str(slots)
                return f"No available slots were found on {specific_date.date()}. However, here are the available slots until {end_of_day.date()} proposal slots: {slots}."
            else:
                return f"No available slots were found on {specific_date.date()} or in the following week until {end_of_day.date()}."
        except Exception as e:
            return f"An error occurred while finding available slots: {e}"

    def find_available_by_specific_date(self, specific_date: datetime) -> List[Dict[str, str]] | str:
        """Return available events on a specific date.
        
        Args:
            specific_date: The specific datetime to check for available slots.
        """

        start = specific_date.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
        end = specific_date.replace(hour=self.end_hour, minute=0, second=0, microsecond=0)
        slots = self._list_available_events(start, end)

        if slots and isinstance(slots, list) and len(slots) > 0:
            return self._format_slots_to_str(slots)

        return self._find_available_slots_after_date(specific_date)
         
    def find_available_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Dict[str, Any]] | str:
        """This function gets events in a date range, it can be the same day and different time or two different days,
        returning a list of available slots between the specified start and end dates.

        Args:
            start_date: The start datetime of the range.
            end_date: The end datetime of the range.
        """

        try:
            start = self._check_valid_date_and_hour_range(start_date)
            end = self._check_valid_date_and_hour_range(end_date)

            if start.date() == end.date():
                slots = self._list_available_events(start, end)
                if slots and isinstance(slots, list) and len(slots) > 0:
                    return self._format_slots_to_str(slots)

            slots = self._list_available_events(start, end)
            if slots and isinstance(slots, list) and len(slots) > 0:
                return self._format_slots_to_str(slots)
            else:
                slots = self._find_available_slots_after_date(end)

                return f"No available slots were found between {start_date} and {end_date}."
        except Exception as e:
            return f"An error occurred while finding available slots: {e}"
    
    def find_available_without_date(self) -> List[Dict[str, str]] | str:
        """Find available slots in the next 7 or 14 business days.
        Returns: a list of available slots with formatted start and end dates.

        Args:
            None
        """

        try:
            start_date = datetime.now()
            start_date = start_date.replace(tzinfo=self.zone)
            if start_date.hour >= self.end_hour:
                start_date = (start_date + timedelta(days=1)).replace(hour=self.start_hour, minute=0, second=0, microsecond=0)
            elif start_date.hour < self.start_hour:
                start_date = start_date.replace(hour=self.start_hour, minute=0, second=0, microsecond=0)

            start_date = self._check_valid_date_and_hour_range(start_date)
            end_date_one_week = start_date + timedelta(days=7)
            end_date_two_weeks = start_date + timedelta(days=14)

            slots = self._list_available_events(start_date, end_date_one_week)
            if slots and isinstance(slots, list) and len(slots) > 0:
                return self._format_slots_to_str(slots)
            
            slots = self._list_available_events(start_date, end_date_two_weeks)
            if slots and isinstance(slots, list) and len(slots) > 0:
                return self._format_slots_to_str(slots)
            
            return f"No available slots were found in the next two weeks."
        except Exception as e:
            return f"An error occurred while finding available slots: {e}"

    def create_or_update_meeting(self, time_min: datetime, time_max: datetime, invite_email: str, titre: str, description: str, mode: str = 'in-person') -> str:
        """Update the event found in the time window [time_min, time_max] by:
            - adding 'Meeting in person at the office' to the description if mode == 'in-person'
            - creating and attaching a Google Meet link if mode == 'online'
            - updating the title and adding the guest (invite_email) to attendees
        Returns: A dict with success status and details or error message.

        Args:
            time_min: datetime, start datetime of slot.
            time_max: datetime, end datetime of slot.
            invite_email: str, guest email to add to the event
            titre: str, new title for the event
            description: str, description for the event
            mode: str, 'online' or 'in-person' indicating the meeting mode
        """
        
        try:
            time_min_rfc = time_min.astimezone(self.zone)
            time_max_rfc = time_max.astimezone(self.zone)

            # Weekend check
            if time_min_rfc.weekday() >= 5:
                return "Cannot schedule meetings on weekends."

            # Working hours check
            if time_min_rfc.hour < self.start_hour or time_max_rfc.hour > self.end_hour:
                return "The provided time window exceeds working hours (9 AM to 6 PM)."

            calendar_id = getattr(self, "calendar_id", "primary")

            # Search for existing event (same day, same title, same attendee)
            day_start = datetime.combine(time_min_rfc.date(), datetime.min.time(), self.zone)
            day_end = day_start + timedelta(days=1)

            events_result = self.service.events().list(
                calendarId=calendar_id,
                timeMin=day_start.isoformat(),
                timeMax=day_end.isoformat(),
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            items = events_result.get('items', [])

            existing_event = None
            for ev in items:
                summary = (ev.get('summary') or '').strip()
                attendees = ev.get('attendees', []) or []
                attendee_emails = {a.get('email') for a in attendees if a.get('email')}
                ev_date = self._parse_rfc3339(ev['start'].get('dateTime') or ev['start'].get('date')).date()
                if summary.lower() == titre.lower() and day_start.date() == ev_date and invite_email.lower() in attendee_emails:
                    existing_event = ev
                    break
            
            # Build base body
            event_body = {
                'summary': titre,
                'description': description,
                'start': {'dateTime': time_min_rfc.isoformat()},
                'end': {'dateTime': time_max_rfc.isoformat()},
                'attendees': [{'email': invite_email}],
            }

            # Conference handling
            if mode == 'online':
                event_body['conferenceData'] = {
                    'createRequest': {
                    'requestId': f"meet-{int(datetime.now().timestamp())}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'},
                    }
                }

            if existing_event:
                # Merge attendees
                existing_attendees = existing_event.get('attendees', []) or []
                existing_emails = {a.get('email') for a in existing_attendees if a.get('email')}
                if invite_email not in existing_emails:
                    existing_attendees.append({'email': invite_email})
                event_body['attendees'] = existing_attendees

                event = self.service.events().update(
                    calendarId=calendar_id,
                    eventId=existing_event['id'],
                    body=event_body,
                    conferenceDataVersion=1,
                    sendUpdates='all'
                ).execute()
                action_type = "updated"
            else:
                for item in items:
                    item_date_start = self._parse_rfc3339(item['start'].get('dateTime') or item['start'].get('date'))
                    item_date_end = self._parse_rfc3339(item['end'].get('dateTime') or item['end'].get('date'))
                    if ((item_date_start <= time_min_rfc <= item_date_end) or 
                        (item_date_start <= time_max_rfc <= item_date_end)):
                        return "The specified time slot overlaps with an existing event. Please choose a different time."
                    
                event = self.service.events().insert(
                    calendarId=calendar_id,
                    body=event_body,
                    conferenceDataVersion=1,
                    sendUpdates='all'
                ).execute()
                action_type = "created"

            if not event:
                return f"Failed to {action_type} the event."
            return f"Success: The meeting has been successfully {action_type}."
        except Exception as e:
            return f"An error occurred while reserving the meeting: {e}"


__all__ = ['CalendarManager']