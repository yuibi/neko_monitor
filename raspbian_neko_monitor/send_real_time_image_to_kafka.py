from kafka import KafkaProducer
import requests
import time

producer = KafkaProducer(bootstrap_servers='x.x.x.x:x')

url = "http://x.x.x.x:x/picture/1/current/"

while True:
    try:
        r = requests.get(url)
    except requests.exceptions.RequestException as e:
        print("Request Error")

    if r.status_code == 200:
        try:
            producer.send('cat_water', r.content)
        except:
            print("Status Code Error")

    producer.flush()

    time.sleep(100)
