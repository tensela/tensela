---
title: Environment
description: The sun for any place and date, shadows, how straight the sun reaches each face, solar energy and sun hours, daylight inside a room, and the climate of a weather file.
---

Environment brings the site into the design: where the sun is, which faces it reaches, how much light gets inside.
These nodes are amber on the canvas.

**Time is local standard time, without summer time.** `13.5` is half past one. The **time zone** is the hours from
UTC without summer time: Madrid `+1`, Montevideo `-3`.

## Sun and shadow

### Sun

![Sun](/images/manual/nodes/sun.png)

**What for.** Where the sun is for a place, a day and an hour, and its path: the solar diagram, the ray of light for
shadows and angles, its altitude and azimuth, sunrise and sunset.

| Input | What it means |
|---|---|
| **location** | a city of the list, or *other place* to give its **latitude**, **longitude** and **time zone** |
| **day**, **month**, **hour** | the moment; each can be a list |
| **scale** | the radius of the diagram and the distance of the sun, in metres |
| **show** | the *diagram*, the *day path*, the *position*, a *beam*, the *ray*, the *altitude*, the *azimuth*, *sunrise*… |

**Tips.**
- The ▶ of the hour, in the panel, plays the day: shadows and angles move with it.
- For **Shadow** and **Incidence**, set **show** to *ray*.

### Shadow

![Shadow](/images/manual/nodes/shadow.png)

**What for.** The shadow of some geometry with the ray of a Sun: on the ground, exact, with its outline and its area;
or on other surfaces (a terrain, a façade), face by face.

| Input | What it means |
|---|---|
| **geometry** | what casts the shadow |
| **ray** | the ray of a Sun; with a list of hours, the shadows of all of them |
| **ground** | the height of the ground |
| **surfaces** | optional: where it falls instead of the ground, face by face |
| **show** | the *shadow*, its *outline*, its *area*, or the faces *sunlit* or *in shadow* |

### Incidence

![Incidence](/images/manual/nodes/incidence.png)

**What for.** How straight the sun reaches each face: 1 when it falls square, 0 when it grazes or comes from behind.
For panels that open or close with the sun, or to see which side of a building gets the sun.

| Input | What it means |
|---|---|
| **faces** | panels, a mesh, a surface or a box |
| **ray** | the ray of a Sun; with a list of hours, their average |
| **side** | *its face* (where each face looks) or *both faces* |
| **show** | *sunlight* (1 to 0) or the *angle* from the face, in degrees |

## Energy and light

### Insolation

![Insolation](/images/manual/nodes/insolation.png)

**What for.** The solar energy each face receives in a period, with what shades it: in kWh/m², the hours of sun, or
how much sky it sees. For passive gain (much sun in winter, little in summer) and to place solar panels. An
estimate for comparing options, not an energy or yield calculation.

| Input | What it means |
|---|---|
| **faces** | what is analysed |
| **obstructions** | optional: what shades it (neighbours, trees, the rest of the building) |
| **climate** | optional: a **Climate** node, for the real sun of each hour; without it, a clear sky |
| **location** and its **latitude**, **longitude**, **time zone** | the place |
| **period** | *year*, *summer*, *winter*, *month* or *day* |
| **show** | *radiation*, *direct*, *diffuse*, *sun hours* or *sky view* |

**Tips.**
- Paint the faces by its value (**Colour → by a value**) to see the result on the building.

### Daylight

**What for.** How much natural light reaches some points inside a room under an overcast sky: the daylight factor,
the lux, and the average and uniformity of the room. A simplified estimate for comparing options; for regulations or
certification, a validated simulation.

| Input | What it means |
|---|---|
| **points** | where it is measured: a grid at desk height, 0.7 to 0.85 m |
| **room** | the room: a box, or its walls, floor and ceiling |
| **glass** | the windows: rectangles on the walls |
| **obstructions** | optional: what blocks the sky outside (louvers, eaves, neighbours) |
| **transmittance** | how much light the glass lets through, in % (double glazing about 70) |
| **reflectance** | how much light the walls reflect, in % (light walls about 70; dark, 30) |
| **show** | *daylight factor*, *illuminance*, *sky component*, *average illuminance*, *average daylight factor* or *uniformity* |

**Tips.**
- As a reference, 2 % is often taken as a well-lit room and 5 % as a very bright one.

### Climate

**What for.** The climate of a place from a weather file (`.epw`): temperature, humidity, sun and wind of each hour of
a typical year. Connected to **Insolation**, the real sun instead of a clear sky.

| Input | What it means |
|---|---|
| **file** | a weather file `.epw`, or the `.zip` it comes in (climate.onebuilding.org) |
| **show** | *temperature*, *humidity*, *radiation*, *wind speed* or *direction*, *cloud cover* |
| **per** | *hour* (8760), *day* (365) or *month* (12) |
