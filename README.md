Irisys Vector 4D MQTT To InfluxDB v1.x
======================================

This code stores data from an [Irisys Vector 4D
sensor](https://www.irisys.net/products/vector4d-people-counter) by pulling data
from MQTT and sending it to an InfluxDB v1.x database.

Data Formats
------------

This script publishes three measurements to InfluxDB.

### 1. `occupancy_count`

The main measurement is `occupancy_count` which is the count of the estimated
number of occupants in the room. The structure of this message looks like:

```
point = {
	"measurement": "occupancy_count",
	"fields": {
		"value": <occupancy count integer>
	}
    "tags": {
    	"method": "vector_4d",
        "device_id": device_id,
        "receiver": "influxdb-mqtt-irisys",
    },
    "time": ts,
}
```

When creating new occupancy streams, use the same measurement name with the
single field "value". Be sure to include a tag called "method" which is set to a
descriptive name for the technique used to generate the occupancy count
estimate.

### 2. `vector_4d_count`

The `vector_4d_count` measurement includes a Vector 4D's register count.

```
point = {
	"measurement": "vector_4d_count",
	"fields": {
		"value": <register value>
	}
    "tags": {
    	"register_name": <register name>,
        "device_id": device_id,
        "receiver": "influxdb-mqtt-irisys",
    },
    "time": ts,
}
```

A separate point will be created for each register.

### 3. `vector_4d_count_occupancy`

The `vector_4d_count_occupancy` measurement includes all of the raw data used to
generate the occupancy estimate.

```
point = {
	"measurement": "vector_4d_count_occupancy",
	"fields": {
		"enter_offset": <Saved Enter offset>,
        "exit_offset": <Saved Exit offset>,
        "enter_count": <Enter>,
        "exit_count": <Exit>,
        "enter": <Enter count after offset>,
        "exit": <Exit count after offset>,
        "occupancy_raw": <Enter - Exit>,
        "occupancy_count": <occupancy count>,
	}
    "tags": {
        "device_id": device_id,
        "receiver": "influxdb-mqtt-irisys",
    },
    "time": ts,
}
```

The `occupancy_raw` value does not check for negative occupancy values.


Configuration
-------------

There are few setup steps required to use this script.

### Vector 4D Setup

The Vector 4D needs to publish to MQTT. We are currently only using the Live
Counts topic, which needs to be set to use the topic name `irisys/<device
id>/live_counts`.

### Configuring This Script

Need two configuration files:

In `/etc/swarm-gateway/influx.conf`:

```
url=<hostname>
port=443
username=<influx username>
password=<influx user password>
database=<database name>
```

and `/etc/swarm-gateway/mqtt.conf`:

```
username=<mqtt username>
password=<mqtt password>
hostname=<mqtt url>
port=8883
```


Other Notes
-----------

This script publishes to a special URL `<influx host>/gateway/write`, rather
than just `/write`. This enables us to add metadata before the data are stored
in the database. You can easily remove this if you do not need it.
