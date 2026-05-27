# Vehicle Type Editing — Modify vehicle_types.add.xml

## When to Use

Use this guide when the user requests:
- Changing vehicle properties (emission standard, acceleration, max speed, etc.)
- Adding new vehicle types (truck, bus, motorcycle, etc.)
- Adjusting fleet composition for scenario analysis

## How It Works

Unlike rerouter and variable speed sign guides, this guide edits an **existing file** rather than creating a new one. The file `vehicle_types.add.xml` is located in the simulation working directory and is automatically loaded by SUMO.

**Workflow**: Read the current file via Filesystem MCP, modify its content, write it back.

Do NOT create a separate vType file — SUMO loads `vehicle_types.add.xml` before user additional files, so duplicate vType IDs in a separate file will be ignored.

## Current Default File Structure

The default `vehicle_types.add.xml` contains three vehicle types:

```xml
<additional>
    <vType id="passenger" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="1,0,0" emissionClass="HBEFA3/PC_G_EU4"/>

    <vType id="electric" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="0,255,0" emissionClass="Energy"/>

    <vType id="gasoline" vClass="passenger"
           accel="2.0" decel="4.0" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="255,0,0" emissionClass="HBEFA3/PC_G_EU4"/>
</additional>
```

## XML Schema: `<vType>`

| Attribute | Required | Type | Default | Description |
|-----------|----------|------|---------|-------------|
| id | Yes | string | — | Unique identifier |
| vClass | No | string | "passenger" | Vehicle class (determines physical defaults) |
| accel | No | float (m/s^2) | 2.6 | Maximum acceleration |
| decel | No | float (m/s^2) | 4.5 | Maximum deceleration |
| maxSpeed | No | float (m/s) | 55.55 | Maximum speed. **Unit is m/s, NOT km/h.** Use the speed reference table below |
| length | No | float (m) | 5.0 | Vehicle length |
| minGap | No | float (m) | 2.5 | Minimum gap to leading vehicle |
| sigma | No | float (0-1) | 0.5 | Driver imperfection (0 = perfect, 1 = maximum randomness) |
| tau | No | float (s) | 1.0 | Desired time headway |
| color | No | string | "1,1,0" | RGB color (0-255 per channel) |
| emissionClass | No | string | "PC_petrol_Euro-4" | Emission model. See reference table below |
| guiShape | No | string | "unknown" | Visual shape in SUMO GUI |

## IMPORTANT: Speed Unit is m/s

**maxSpeed must be in meters per second (m/s), NOT km/h.**

Use the reference table below. Do NOT attempt to calculate conversions manually.

### Speed Reference Table (km/h to m/s)

| km/h | m/s   |
|------|-------|
| 10   | 2.78  |
| 20   | 5.56  |
| 30   | 8.33  |
| 40   | 11.11 |
| 50   | 13.89 |
| 60   | 16.67 |
| 70   | 19.44 |
| 80   | 22.22 |
| 90   | 25.00 |
| 100  | 27.78 |
| 110  | 30.56 |
| 120  | 33.33 |

## vClass Reference

| vClass | Description | Typical length | Typical maxSpeed |
|--------|-------------|---------------|-----------------|
| passenger | Passenger car | 5.0 m | 50-70 m/s |
| truck | Heavy truck | 12.0 m | 22-25 m/s |
| bus | City bus | 12.0 m | 19-22 m/s |
| coach | Long-distance bus | 14.0 m | 25-28 m/s |
| delivery | Delivery van | 6.5 m | 25-33 m/s |
| motorcycle | Motorcycle | 2.2 m | 44-56 m/s |
| bicycle | Bicycle | 1.8 m | 5.56-8.33 m/s |
| emergency | Emergency vehicle | 6.5 m | 39-44 m/s |
| taxi | Taxi | 5.0 m | 50-70 m/s |

## emissionClass Reference

### HBEFA3 Format (currently used in default file)
| Class | Description |
|-------|-------------|
| HBEFA3/PC_G_EU4 | Passenger car, gasoline, Euro-4 |
| HBEFA3/PC_G_EU6 | Passenger car, gasoline, Euro-6 |
| HBEFA3/PC_D_EU4 | Passenger car, diesel, Euro-4 |
| HBEFA3/PC_D_EU6 | Passenger car, diesel, Euro-6 |
| HBEFA3/HDV_D_EU4 | Heavy-duty vehicle, diesel, Euro-4 |
| HBEFA3/HDV_D_EU6 | Heavy-duty vehicle, diesel, Euro-6 |
| HBEFA3/Bus | Bus |

### HBEFA4 Format
| Class | Description |
|-------|-------------|
| HBEFA4/PC_petrol_Euro-4 | Passenger car, gasoline, Euro-4 |
| HBEFA4/PC_petrol_Euro-6d | Passenger car, gasoline, Euro-6d |
| HBEFA4/PC_diesel_Euro-6d | Passenger car, diesel, Euro-6d |
| HBEFA4/PC_BEV | Passenger car, battery electric |
| HBEFA4/PC_PHEV_petrol_Euro-6d | Plug-in hybrid, gasoline, Euro-6d |
| HBEFA4/RT_diesel_Euro-6d | Rigid truck, diesel, Euro-6d |
| HBEFA4/UBus_diesel_Euro-6d | Urban bus, diesel, Euro-6d |
| HBEFA4/Coach_diesel_Euro-6d | Coach bus, diesel, Euro-6d |

### Special Classes
| Class | Description |
|-------|-------------|
| Energy | Electric vehicle (zero tailpipe emissions) |
| zero | No emissions at all |

## Examples

### Example 1: Upgrade Emission Standard

Change the default passenger car from Euro-4 to Euro-6:

```xml
<additional>
    <vType id="passenger" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="1,0,0" emissionClass="HBEFA4/PC_petrol_Euro-6d"/>

    <vType id="electric" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="0,255,0" emissionClass="Energy"/>

    <vType id="gasoline" vClass="passenger"
           accel="2.0" decel="4.0" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="255,0,0" emissionClass="HBEFA4/PC_petrol_Euro-6d"/>
</additional>
```

### Example 2: Add Truck Type

Add a truck type to the existing file:

```xml
<additional>
    <vType id="passenger" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="1,0,0" emissionClass="HBEFA3/PC_G_EU4"/>

    <vType id="electric" vClass="passenger"
           accel="2.5" decel="4.5" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="0,255,0" emissionClass="Energy"/>

    <vType id="gasoline" vClass="passenger"
           accel="2.0" decel="4.0" sigma="0.5" length="5.0" minGap="2.5" maxSpeed="70"
           color="255,0,0" emissionClass="HBEFA3/PC_G_EU4"/>

    <vType id="truck" vClass="truck"
           accel="1.3" decel="4.0" sigma="0.5" length="12.0" minGap="3.0" maxSpeed="22.22"
           color="0,0,255" emissionClass="HBEFA4/RT_diesel_Euro-6d"/>
</additional>
```

Note: After adding a new vType, vehicles in the route file must reference its `id` (e.g., `type="truck"`) for it to be used. Use `vehicle_type_edit_tool` or edit the route file to assign vehicles to the new type.

### Example 3: Add Bus Type

```xml
    <vType id="bus" vClass="bus"
           accel="1.2" decel="4.0" sigma="0.5" length="12.0" minGap="3.0" maxSpeed="19.44"
           color="255,165,0" emissionClass="HBEFA4/UBus_diesel_Euro-6d"/>
```

## Constraints

- Each `id` must be unique within the file.
- The file must contain the complete set of vTypes (existing + new). Do not write only the new type.
- Adding a new vType does not automatically assign vehicles to it. The route file must also be updated.
- maxSpeed is in **m/s**. Use the speed reference table above.
- The root element must be `<additional>`.

## AgentSUMO Workflow

1. Read the current `vehicle_types.add.xml` via Filesystem MCP.
2. Modify the content (change attributes or add new vType elements).
3. Write the complete file back via Filesystem MCP. The file path is the same as the original.
4. If new vTypes were added, assign vehicles to them using `vehicle_type_edit_tool` or by editing the route file.
5. Run `sumo_runner` as normal — `vehicle_types.add.xml` is automatically loaded.
