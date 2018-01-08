import RPi.GPIO as GPIO
from time import sleep
from kafka import KafkaProducer
import requests

producer = KafkaProducer(bootstrap_servers='x.x.x.x:x')

url = "http://x.x.x.x:x/picture/1/current/"

GPIO.setmode(GPIO.BCM)  # Configures pin numbering to Broadcom reference

GPIO.setup(17, GPIO.OUT)  # Set our GPIO pin to output
GPIO.output(17, False)  # Set output to off

# Set GPIO pin to input and activate pull_down resistor
GPIO.setup(14, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

print ("Motion Sensor Test")
sleep(2)
print ("Ready")

try:

    while True:
        if GPIO.input(14):
            GPIO.output(17, True)  # Turn LED on
            print ("Sensor Triggered")

            try:
                r = requests.get(url)
            except requests.exceptions.RequestException as e:
                print("Request Error")

            if r.status_code == 200:
                try:
                    producer.send('cat_motion', r.content)
                except:
                    print("Status Code Error")

            producer.flush()

            sleep(5)

        else:
            GPIO.output(17, False)  # Turn LED off

except KeyboardInterrupt:  # catch that ctrl+C has been pressed
    print ("Shutting Down")

except:
    print("An Error or Exception has occured")

finally:  # set used GPIO pins to inputs
    print ("Resetting GPIO pins")
    GPIO.cleanup()
