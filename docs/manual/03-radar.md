# Radar

> Why a target is seen, and why it is not

Every detection in the game is computed, not scripted. When a radar's simulated antenna sweeps past an aircraft, the simulation works out the geometry, the signal, the interference and the odds, then rolls the dice. The coverage analysis on the Tracks console shows the same calculation for any track, with the reason a radar cannot see it.

## The radar equation

Echo power falls with the **fourth power of range**: double the distance and the signal drops 12 dB. Signal-to-noise depends on the transmitter's power, the antenna's gain, the wavelength, the pulse, the receiver's noise and the target's **radar cross-section**, which changes with aspect. A bomber seen broadside is a far bigger target than the same bomber nose-on; a cruise missile is smaller than either. Each radar type is calibrated against its documented detection range.

While the beam sweeps across a target it collects several pulses, more of them when the antenna turns slowly. **Faster rotation** means more frequent updates but less signal per look.

## Fluctuation and threshold

A real echo flickers from scan to scan as the aircraft's aspect changes (the Swerling I model). Near maximum range a target may paint on one sweep and vanish on the next.

The operator sets the **detection threshold** as a false-alarm probability. At 1E-4 the radar finds weaker targets but fills the scope with noise and false plots, which can start false tracks. At 1E-8 the picture is clean, and deaf.

## The horizon

Microwaves travel in nearly straight lines, bent slightly by the atmosphere: the 4/3-Earth model. A radar 100 m up sees a target at 300 m only out to about 110 km, however powerful it is. **Low flyers hide below the horizon.** That is the whole tactical reason for flying low.

The weather changes the bending. A temperature inversion can trap the beam in a **duct** and carry it far beyond the normal horizon, along with sea clutter and ghost returns.

## Terrain

Mountains cast radar shadows. Each site's horizon is computed from real elevation data (ETOPO1), azimuth by azimuth. The coverage overlay (`C`) shows what the network can see at the altitude you choose with `[` and `]`.

## Lobing

Long-wavelength radars, such as the Soviet P-8, P-10, P-12 and P-14, receive the direct echo and a second one reflected off the ground. The two interfere, forming lobes with gaps between them, and coverage close to the ground is poor.

## Clutter and MTI

Ground and sea echoes swamp targets at short range. **Moving Target Indication** cancels echoes that do not move. It also cancels targets with no radial speed: an aircraft flying across the beam sits in the *tangential notch*. And it cancels targets at **blind speeds**, multiples of wavelength × PRF ÷ 2. MTI on near the coast, off when you are hunting something slow.

## Pulse-Doppler and look-down

Airborne radars look down into the ground. The AN/APY-1 of the E-3A sees a low-flying bomber over land or sea at long range because it sorts echoes by their Doppler shift; ground clutter sits at zero Doppler and is rejected. It has a notch too: an aircraft flying across its line of sight has no Doppler shift either, and disappears into the clutter filter.

Early interceptor radars have **no look-down capability**. Under a low target, they see the ground.

## Height

Search radars give range and bearing. Altitude comes from elsewhere.

- **Nodding height finders** (US AN/FPS-6 and FPS-26, Soviet PRV-11 and PRV-13) sweep a narrow beam up and down through one target at a time. They are accurate, but a queue builds behind them. Ask for heights on the tracks that matter.
- **V-beam radars** (P-20, P-30) carry a slanted second beam and estimate the altitude of every target on every scan, coarsely.
- **3D radars** (AN/FPS-117, ST-68U, the airborne APY-1) measure elevation directly.
- A **visual identification** gives an altitude too, and so does Mode C on a later transponder.

## IFF and SIF

Military aircraft answer an interrogator with coded replies. US Selective Identification Feature: Mode 1 (mission), Mode 2 (unit), Mode 3 (the code air traffic control also uses). Soviet Kremniy: codes that change every month, so a squadron that has not changed its code on the first of the month answers wrongly. A civil aircraft may have no compatible transponder at all, or a failed one.

## Faults

Radars break. A site can be **degraded** (losing sensitivity), **down** for repair, or taken off the air for **scheduled maintenance**, which costs coverage now and saves a failure later. A radar's data reaches the command post only over its line, and lines fail too.
