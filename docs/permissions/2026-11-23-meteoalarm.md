# MeteoAlarm: the daily weather snapshot is allowed, on conditions (23 Nov 2026)

**Status: allowed, on four conditions plus "a morning snapshot, not a live warning service" (all met, spec §11; #115).** This answers the owner's question (spec §11, checklist #43): is a daily, dated 06:45 snapshot, labelled "not live" and linking to meteoalarm.org, allowed, given the Terms' ≤ 10 min real-time requirement for operational use?

- **From:** the MeteoAlarm Team (no individual name given)
- **Date:** 23 November 2026
- **In reply to:** the owner's email about the daily snapshot
- Email address left out on purpose: this repo is public.

## Their reply

> In principle, we are supportive of your proposed use of the warning information, particularly given the non-commercial nature of your project. Displaying the KNMI warning level for Zuid-Holland once daily, provided that it is clearly identified as a morning snapshot and not a live warning service, seems like a reasonable approach. We would ask that you ensure the following:
>
> - Appropriate attribution to MeteoAlarm and KNMI.
> - Inclusion of the relevant disclaimer accompanying the displayed information.
> - A clear link to the official MeteoAlarm website for the latest warnings.
> - No suggestion that Haven Daily is an official MeteoAlarm or KNMI service.

## How each condition is met

| Condition | On the weather dial (every day page) | On How it works |
|---|---|---|
| A morning snapshot, not a live warning service | "Warnings at 06:45 · not live" (read time), and the line "Morning snapshot, not live"; under "Details": "Morning snapshot, not a live warning service." (#173) | "…a morning snapshot, not a live warning service" |
| Attribution to MeteoAlarm and KNMI | "KNMI via MeteoAlarm" (linked) and KNMI's own level, e.g. "KNMI: Code yellow · Wind → Watch" | "issued by KNMI … from www.meteoalarm.org"; credits: "Weather warnings by KNMI via MeteoAlarm" |
| The relevant disclaimer | MeteoAlarm's disclaimer, verbatim, always visible | the same, verbatim |
| A clear link for the latest warnings | "Latest warnings on meteoalarm.org" → https://www.meteoalarm.org | "always check the latest warnings on www.meteoalarm.org" (linked) |
| Not an official MeteoAlarm or KNMI service | in the short line: "Not a MeteoAlarm or KNMI service"; under "Details": "Haven Daily is not a MeteoAlarm or KNMI service." (#173) | "Haven Daily is an independent project, not a MeteoAlarm or KNMI service" (the word "official" never appears on How it works, so nothing on it reads as official) |

The dial shows all of these also when there are no warnings and on "No data". Only the level and the hazard are shown, never the warning text (spec §2.2). Tests: `tests/test_meteoalarm_permission.py`.

## Follow-up

*(none)*
