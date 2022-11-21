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

    point_template = {
        "tags": {
            "device_id": device_id,
            "receiver": "influxdb-mqtt-irisys",
        },
        "time": time.time_ns(),
    }

    if data_type == "live_counts":
        counts = json.loads(msg.payload)
        for count in counts["counts"]:
            val = count["count"]
            name = count["name"]

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

client.tls_set()
client.username_pw_set(mqtt_config["username"], mqtt_config["password"])
client.connect(mqtt_config["hostname"], int(mqtt_config["port"]), 60)

# Continuously receive MQTT messages.
client.loop_forever()