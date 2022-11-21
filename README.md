Irisys Vector 4D MQTT To InfluxDB v1.x
======================================

This code stores data from an [Irisys Vector 4D
sensor](https://www.irisys.net/products/vector4d-people-counter) by pulling data
from MQTT and sending it to an InfluxDB v1.x database.

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
