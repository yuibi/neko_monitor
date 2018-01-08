from kafka import KafkaProducer
import time
import json
from Adafruit_BME280 import *

sensor = BME280(t_mode=BME280_OSAMPLE_8, p_mode=BME280_OSAMPLE_8, h_mode=BME280_OSAMPLE_8)
producer = KafkaProducer(bootstrap_servers='x.x.x.x:x')

while True:
    degrees = sensor.read_temperature()
    humidity = sensor.read_humidity()

    value = {
        "temperature" : round(degrees, 2),
        "humidity" : round(humidity, 2)
    }

    msg = json.dumps(value).encode("utf-8")
    producer.send('cat_temp_humidity', msg)
    producer.flush()

    time.sleep(300)
