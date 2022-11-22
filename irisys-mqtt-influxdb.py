#!/usr/bin/env python3

import arrow
import copy
import datetime
import json
import re
import sys
import time

import influxdb
from influxdb import line_protocol
import paho.mqtt.client as mqtt


MQTT_CONFIG_FILE_PATH = "/etc/swarm-gateway/mqtt.conf"
INFLUX_CONFIG_FILE_PATH = "/etc/swarm-gateway/influx.conf"

# Get awair device info
mqtt_config = {}
with open(MQTT_CONFIG_FILE_PATH) as f:
    for l in f:
        fields = l.split("=")
        if len(fields) == 2:
            k = fields[0].strip()
            v = fields[1].strip()
            mqtt_config[k] = v

# Get influxDB config.
influx_config = {}
with open(INFLUX_CONFIG_FILE_PATH) as f:
    for l in f:
        fields = l.split("=")
        if len(fields) == 2:
            influx_config[fields[0].strip()] = fields[1].strip()


# The callback for when the client receives a CONNACK response from the server.
def on_connect(client, userdata, flags, rc):
    print("Connected with result code {}".format(rc))

    # Subscribing in on_connect() means that if we lose the connection and
    # reconnect then subscriptions will be renewed.
    client.subscribe("irisys/#")


# Keep a copy of the last values so we can re-submit the same values.
saved_data = {}


# The callback for when a PUBLISH message is received from the server.
def on_message(client, userdata, msg):
    # print("{}: {}".format(msg.topic, str(msg.payload)))

    topic_fields = msg.topic.split("/")
    # We expect "irisys/<id>/<topic>"
    if len(topic_fields) != 3 or topic_fields[0] != "irisys":
        print("unknown topic name: {}".format(msg.topic))
        return

    device_id = topic_fields[1]
    data_type = topic_fields[2]

    points = []

    # Support older versions of python
    ts = int(time.time() * 1000000000)
    # ts = time.time_ns() # 3.7+

    point_template = {
        "tags": {
            "device_id": device_id,
            "receiver": "influxdb-mqtt-irisys",
        },
        "time": ts,
    }

    if data_type == "live_counts":
        counts = json.loads(msg.payload.decode("utf-8"))
        for count in counts["counts"]:
            val = count["count"]
            name = count["name"]

            # Save this value.
            if not device_id in saved_data:
                saved_data[device_id] = {}
            saved_data[device_id][name] = val

            point = copy.deepcopy(point_template)

            point["measurement"] = "vector_4d_count_test"
            point["fields"] = {"value": val}
            point["tags"]["register_name"] = name

            points.append(point)

    elif data_type == "counts":
        # Ignore whatever comes in this MQTT message. Just use this as an event
        # to re-send the last data.

        if device_id in saved_data:
            print("resending for {}".format(device_id))
            for name, val in saved_data[device_id].items():
                point = copy.deepcopy(point_template)

                point["measurement"] = "vector_4d_count_test"
                point["fields"] = {"value": val}
                point["tags"]["register_name"] = name

                points.append(point)

    else:
        # Ignore all other topics for now.
        pass

    if len(points) == 0:
        return

    data = {"points": points}

    data = influxdb.line_protocol.make_lines(data, None).encode("utf-8")
    params = {
        "db": influx_client._database,
        "u": influx_config["username"],
        "p": influx_config["password"],
    }
    headers = influx_client._headers.copy()

    influx_client.request(
        url="gateway/write",
        method="POST",
        params=params,
        data=data,
        expected_response_code=204,
        headers=headers,
    )
    print("wrote points received from MQTT")


# Influx DB client
influx_client = influxdb.InfluxDBClient(
    influx_config["url"],
    influx_config["port"],
    influx_config["username"],
    influx_config["password"],
    influx_config["database"],
    ssl=True,
    gzip=True,
    verify_ssl=True,
)

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

if int(mqtt_config["port"]) > 2000:
    client.tls_set()
client.username_pw_set(mqtt_config["username"], mqtt_config["password"])
client.connect(mqtt_config["hostname"], int(mqtt_config["port"]), 60)

# Continuously receive MQTT messages.
client.loop_forever()
