from __future__ import annotations
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta, timezone
from googleapiclient.errors import HttpError
from models.authentication import Authenticator


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
        self.zone = datetime.now().astimezone().tzinfo
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
                print("Same day range")
                slots = self._list_available_events(start, end)
                if slots and isinstance(slots, list) and len(slots) > 0:
                    return self._format_slots_to_str(slots)

            slots = self._list_available_events(start, end)
            print(f"Slots found between {start_date} and {end_date}")
            if slots and isinstance(slots, list) and len(slots) > 0:
                print("Slots found in range")
                return self._format_slots_to_str(slots)
            else:
                print("No slots found in range")
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

    def confirmation_meeting(self, time_min: datetime, time_max: datetime, invite_email: str, titre: str, mode: str = 'presentiel') -> Dict[str, Any] | str:
        """Update the event found in the time window [time_min, time_max] by:
            - adding 'Meeting in person at the office' to the description if mode == 'presentiel'
            - creating and attaching a Google Meet link if mode == 'online'
            - updating the title and adding the guest (invite_email) to attendees
        Returns: A dict with success status and details or error message.

        Args:
            time_min: datetime, start of the time window to search for the event
            time_max: datetime, end of the time window to search for the event
            invite_email: str, guest email to add to the event
            titre: str, new title for the event
            mode: str, 'online' or 'presentiel' indicating the meeting mode
        """

        # 1) Search for the event in the given time window
        try:
            time_min_rfc = time_min.replace(tzinfo=self.zone)
            time_max_rfc = time_max.replace(tzinfo=self.zone)
        except Exception as e:
            return {"success": False, "error": f"Invalid timestamp: {e}"}

        calendar_id = getattr(self, "calendar_id", "primary")
        
        try:
            tz = time_min_rfc.tzinfo or self.zone
            start_s = datetime.combine(time_min_rfc.date(), datetime.min.time(), tz)
            end_e = start_s + timedelta(days=1)

            resp = self.service.events().list(
                calendarId=calendar_id,
                timeMin=start_s.isoformat(),
                timeMax=end_e.isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=100
            ).execute()
            items = (resp or {}).get("items", [])

            availables = []
            for ev in items:
                s = ev.get("start", {}).get("dateTime")
                e = ev.get("end", {}).get("dateTime")
                if not s or not e:
                    continue
                try:
                    s_dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                    e_dt = datetime.fromisoformat(e.replace("Z", "+00:00"))
                    if s_dt and e_dt:
                        title = ev.get("summary", "(no title)")
                        if ((title and title == "Available") and
                            s_dt.date() == time_min_rfc.date() and
                            e_dt.date() == time_max_rfc.date() and
                            s_dt.hour == time_min_rfc.hour and
                            e_dt.hour == time_max_rfc.hour and
                            s_dt.minute == time_min_rfc.minute and
                            e_dt.minute == time_max_rfc.minute
                        ):
                            availables.append(ev)
                except Exception:
                    continue
            items = availables
        except HttpError as e:
            return {"success": False, "error": f"Error while searching events: {e}"}

        if not items:
            return {"success": False, "error": "No event found in the provided time window."}

        # 2) Choose the event 
        chosen = items[0] if items else None
        event_id = chosen["id"]
        try:
            start_date = chosen.get("start", {}).get("dateTime")
            start_date = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_date = chosen.get("end", {}).get("dateTime")
            end_date = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
            if not start_date or not end_date:
                time_min_rfc = start_date.replace(tzinfo=self.zone)
                time_max_rfc = end_date.replace(tzinfo=self.zone)
        except Exception as e:
            return {"success": False, "error": f"Invalid timestamp: {e}"}

        # 3) Prepare modifications
        mode_norm = (mode or "").strip().lower()
        if mode_norm not in ("online", "presentiel"):
            return {"success": False, "error": "Invalid 'mode'. Use 'online' or 'presentiel'."}

        description = chosen.get("description", "") or ""
        if mode_norm == "presentiel":
            add_desc = "Meeting in person at the office."
        else:
            add_desc = "Meeting online meeting (Google Meet)."

        if add_desc not in description:
            description = f"{description.rstrip()}\n{add_desc}".strip()

        attendees = chosen.get("attendees", []) or []
        emails_existants = {a.get("email", "").lower() for a in attendees}
        if invite_email and invite_email.lower() not in emails_existants:
            attendees.append({"email": invite_email})

        body_patch = {
            "summary": titre,
            "description": description,
            "attendees": attendees,
        }

        # 4) If online, request Meet link creation via conferenceData
        wants_meet = mode_norm == "online"
        if wants_meet:
            body_patch["conferenceData"] = {
                "createRequest": {
                    "conferenceSolutionKey": {"type": "hangoutsMeet"},
                    "requestId": f"meet-{event_id}",
                }
            }

        # 5) Patch the event
        try:
            if wants_meet:
                updated = self.service.events().patch(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=body_patch,
                    conferenceDataVersion=1,
                ).execute()
            else:
                updated = self.service.events().patch(
                    calendarId=calendar_id,
                    eventId=event_id,
                    body=body_patch,
                ).execute()
        except HttpError as e:
            return {"success": False, "error": f"Error while updating event: {e}"}

        # 6) Retrieve Meet link (if online)
        meet_link = None
        if wants_meet:
            meet_link = updated.get("hangoutLink")
            if not meet_link:
                entry_points = (updated.get("conferenceData") or {}).get("entryPoints") or []
                for ep in entry_points:
                    if ep.get("entryPointType") in ("video", "more"):
                        meet_link = ep.get("uri")
                        if meet_link:
                            break

        return {
            "success": True,
            "event": "The event has been successfully updated."
        }


__all__ = ['CalendarManager']