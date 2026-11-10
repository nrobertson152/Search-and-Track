# The Network

> Lines, computers, faults and alerts

An air defense system is a network, and networks fail at their joints.

## Lines

Every radar, base and battery talks to you over a line: a data line, a telephone line, a teletype circuit. Each has a delay, and each can go down. A radar whose line is down sees perfectly well and tells you nothing. A base whose line is down cannot be ordered to scramble. Lines come back after repair; the Network board and the Status console show which are down and for how long.

## The AN/FSQ-7 (US)

The SAGE computer runs as a **duplex**: two complete machines, A and B, one active and one on standby. When the active side fails, the computer stops: no new tracks, no data link, the display frozen. The standby side takes over only when you order the **switchover** on the Radar console's duplex panel, and the change itself takes a little while. The failed side goes to maintenance. Check the duplex lamps when an alarm sounds.

## Radar faults and maintenance

Sites fail, degrade and recover. The technical position can be automated, or you can run it: MAINT 30 MIN takes a site off the air for scheduled maintenance, which costs coverage now and lowers the risk of a failure later. Plan maintenance for the quiet hours, and not on the site that covers the gap everyone else leaves.

## Alerts

Important messages need **acknowledgement**: the COMMS tab shows the number waiting, and higher headquarters notices when you leave them. `A` acknowledges all of them at once, which is quick and a little careless.

## Weather

- **Ducting** extends the horizon, brings sea clutter and ghosts.
- **Rain** cells paint on the shorter-wavelength radars and hide what is inside them.
- **Cloud and night** shorten the pilots' visual range; a very low ceiling stops scrambles.
- **Wind** drifts balloons.

## Time

Time compression runs up to 32×. It drops to real time on alerts, so nothing important passes unseen. The simulation is deterministic: the same orders at the same moments give the same shift.
