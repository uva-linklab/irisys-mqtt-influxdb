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


# This is not a stateless processor so we must save some state as we collect data.
# This looks like:
#
#   state[<device_id>] = {
#        "data": {
#           "<count_name>": <count_value>
#        },
#        "occupancy_count": <count>,
#        "offset": {
#           "saved": bool,
#           "data": {
#               "<count_name>": <count_value>
#           }
#        }
#   }
#
# We need to keep a copy of the last values so we can re-submit the same values.
# We also keep an offset every night to reset the counters to 0. Mark when we
# save the offset at ~4am so we only save it once.
state = {}

# # Keep a copy of the last values so we can re-submit the same values.
# saved_data = {}

# offset_saved = {}
# offsets = {}


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

    # Init fields
    if not device_id in state:
        state[device_id] = {
            "data": {},
            "occupancy_count": 0,
            "offset": {"saved": False, "data": {}},
        }

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

    # By default we do not save the offset. We only save once per day at
    # 4am.
    save_offsets = False

    # If it is newly 4am, we assume the room is empty and save the
    # current counts as an offset.
    if (
        state[device_id]["offset"]["saved"] == False
        and datetime.datetime.now().hour == 4
    ):
        # On this data packet we do want to save the current value as the offset
        # to use for the next 24 hours when calculating occupancy.
        save_offsets = True
    elif datetime.datetime.now().hour == 5:
        # At 5am (and for the entire hour) we reset our saved marker
        state[device_id]["offset"]["saved"] = False

    if data_type == "live_counts":
        counts = json.loads(msg.payload.decode("utf-8"))

        for count in counts["counts"]:
            val = count["count"]
            name = count["name"]

            # Save this value.
            state[device_id]["data"][name] = val

            # Optionally save this value as the offset. This case will likely
            # never happen as we should not get a live count in the middle of
            # the night. We should save this in the "counts" section below.
            if save_offsets:
                state[device_id]["offset"]["data"][name] = val
                print("saving {}:{} for {} (live counts)".format(name, val, device_id))
                state[device_id]["offset"]["saved"] = True

            point = copy.deepcopy(point_template)

            point["measurement"] = "vector_4d_count"
            point["fields"] = {"value": val}
            point["tags"]["register_name"] = name

            points.append(point)

        # We also want to calculate occupancy. We assume there will be two
        # counts: "Enter" and "Exit".
        if "Enter" in state[device_id]["data"] and "Exit" in state[device_id]["data"]:
            enter_offset = state[device_id]["offset"]["data"].get("Enter", 0)
            exit_offset = state[device_id]["offset"]["data"].get("Exit", 0)

            enter = state[device_id]["data"]["Enter"] - enter_offset
            exit = state[device_id]["data"]["Exit"] - exit_offset

            # After compensating for count drift, calculate occupancy is just
            # subtracting the number of exits from the number of enters, and
            # then doing a simple sanity check that occupancy is not negative.
            occupancy = int(enter - exit)
            if occupancy < 0:
                occupancy = 0

            # Save occupancy count point.
            point = copy.deepcopy(point_template)
            point["measurement"] = "occupancy_count"
            point["fields"] = {"value": occupancy}
            # Mark how we calculated this occupancy value.
            point["tags"]["method"] = "vector_4d"
            points.append(point)

            # Save this occupancy count so we can re-send it.
            state[device_id]["occupancy_count"] = occupancy

            # Save additional data for metadata and other reasons.
            point = copy.deepcopy(point_template)
            point["measurement"] = "vector_4d_count_occupancy"
            point["fields"] = {
                "enter_offset": enter_offset,
                "exit_offset": exit_offset,
                "enter_count": state[device_id]["data"]["Enter"],
                "exit_count": state[device_id]["data"]["Exit"],
                "enter": enter,
                "exit": exit,
                "occupancy_raw": enter - exit,
                "occupancy_count": occupancy,
            }
            points.append(point)

    elif data_type == "counts":
        # Ignore whatever comes in this MQTT message. Just use this as an event
        # to re-send the last data.

        if device_id in state:
            # print("resending for {}".format(device_id))
            for name, val in state[device_id]["data"].items():
                # If we are saving offsets do that here.
                if save_offsets:
                    state[device_id]["offset"]["data"][name] = val
                    print("saving {}:{} for {}".format(name, val, device_id))
                    state[device_id]["offset"]["saved"] = True

                point = copy.deepcopy(point_template)

                point["measurement"] = "vector_4d_count"
                point["fields"] = {"value": val}
                point["tags"]["register_name"] = name

                points.append(point)

            point = copy.deepcopy(point_template)
            point["measurement"] = "occupancy_count"
            point["fields"] = {"value": state[device_id]["occupancy_count"]}
            # Mark how we calculated this occupancy value.
            point["tags"]["method"] = "vector_4d"
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
