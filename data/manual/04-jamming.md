# Electronic Countermeasures

> Noise, strobes, channels and burn-through

A noise jammer transmits on the radar's own frequencies so that the receiver hears noise instead of echoes. It does not make the bomber invisible; it makes it impossible to say how far away it is.

## The strobe

A jammer inside the main beam paints a bright spoke along its bearing on the scope: the **jamming strobe**. Every range cell on that bearing is full of noise, so targets behind it are masked. In the sidelobes the jammer is weaker, and other bearings stay usable.

The strobe gives a bearing and nothing else. Two radars hearing the same jammer give two bearings; where they cross, the computer builds a **jammer track**. It has no height and its range is only as good as the crossing angle. Bearings that cross at less than about 15° do not fix anything. Jammer tracks are marked with a J.

## Barrage and spot

A **barrage jammer** spreads its power across a whole band (L and S, say). Every radar in that band is jammed, more weakly.

A **spot jammer** puts all its power on one radar channel: strong but narrow. A radar on another channel is not affected. The jammer must hunt for a radar that changes channel, which takes it about a minute, and it can sit on only one channel at a time. The game's spot jammers tune to the nearest radar.

**Changing channel** (FREQ CHANNEL on the Radar console) buys a minute of clean video. Keeping neighbouring radars on **different channels** means a single spot jammer cannot cover them all.

**Frequency-agile** radars (AN/FPS-27, P-37, AN/FPS-117) hop channels on their own, which spreads a spot jammer's effect thin.

## Frequency diversity

A jammer covers some bands, not all. The AN/FPS-6 height finder works in the S band and is untouched by an L-band jammer. The PVO's metre-wave radars (P-10, P-12, P-14) sit far outside a centimetric jammer's reach. Both services built networks with many radars on many wavelengths for exactly this reason. When one band is blinded, look at the others.

## Burn-through

The echo grows with the inverse fourth power of range; the noise received from a jammer aboard the target grows only with the inverse square. Close enough, the echo wins: that is **burn-through**. Against a strong main-beam jammer, it may come only at short range.

## What jamming tells you

An active jammer is evidence. Higher authority treats a jamming source as hostile in intent: a request to declare it hostile is answered on that basis, and the recommended identity for a jammer track is SUSPECT.
