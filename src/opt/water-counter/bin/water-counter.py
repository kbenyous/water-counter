#!/opt/water-counter/virtualenv/bin/python3
# -*- coding: UTF-8 -*-

import configparser
import paho.mqtt.client as mqtt
import sdnotify
import logging
import time


logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')

def on_total_message(client, userdata, message):
    try:
        parsed_message = int(message.payload)
        logging.debug("Updating in-memory index value to {} liters".format(parsed_message))
        userdata["water_index"] = parsed_message
    except ValueError as e:
        logging.error(e)

def on_count_message(client, userdata, message):
    try:
        parsed_message = int(message.payload)
        if(parsed_message > 0):
            logging.debug("Received message from sensor, adding {} liter(s)".format(parsed_message))
            userdata["water_index"] += parsed_message
            client.publish(userdata["total_queue"], payload=str(userdata["water_index"]), qos=2, retain=True)

        userdata["sd_notifier"].notify('WATCHDOG=1')
    except ValueError as e:
        logging.error(e)


def main():

    # Notifications pour SystemD
    systemd_notifier = sdnotify.SystemdNotifier()

    # Lecture de la conf
    systemd_notifier.notify('RELOADING=1')
    config = configparser.RawConfigParser()
    config.read('/etc/water-counter/water-counter.conf')

    # Configuration du client mqtt
    mqtt_broker_hostname = config.get('mqtt_broker', 'hostname', fallback='localhost')
    mqtt_broker_port = config.getint('mqtt_broker', 'port', fallback=1883)
    mqtt_client_name = config.get('mqtt_broker', 'client_name', fallback='water-counter')
    logging.info("Connecting to MQTT broker {}:{}...".format(mqtt_broker_hostname, mqtt_broker_port))

    # Définition des files d'entrée / sortie
    count_queue = config.get('water_counter', 'count_queue', fallback="house/sensors/water/Count")
    total_queue = config.get('water_counter', 'total_queue', fallback="house/sensors/water/Total")
    status_queue = config.get('water_counter', 'status_queue')

    client = mqtt.Client(mqtt_client_name)
    # Préparation des user_data transmises aux callbacks du client mqtt
    client_user_data = dict()
    client_user_data["total_queue"] = total_queue
    client_user_data["status_queue"] = status_queue
    client_user_data["sd_notifier"] = systemd_notifier
    client_user_data["water_index"] = 0
    client.user_data_set(client_user_data)

    client.on_connect = on_connect
    client.will_set(status_queue, payload="Connection Lost", qos=2, retain=True)
    client.connect(mqtt_broker_hostname, mqtt_broker_port)
    client.loop_start()
    
    systemd_notifier.notify('READY=1')

    # Abonnement aux files d'entrée
    client.subscribe([ (total_queue, 2),
                       (count_queue, 2)])
    # Ajout de callbacks spécifiques
    client.message_callback_add(total_queue, on_total_message)
    client.message_callback_add(count_queue, on_count_message)

    while True:
        time.sleep(20)
        systemd_notifier.notify('WATCHDOG=1')


def on_connect(client, userdata, flags, rc):
    logging.info("Connected to broker")
    client.publish(userdata["status_queue"], payload="Connected", qos=2, retain=True)


if __name__ == '__main__':
    main()

