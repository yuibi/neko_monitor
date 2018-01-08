import os
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-streaming-kafka-0-8_2.11:2.0.2 pyspark-shell'  

from pyspark import SparkContext 
from pyspark.streaming.kafka import KafkaUtils 
from pyspark.streaming import StreamingContext
from pyspark.sql import SparkSession, Row

sc = SparkContext(appName="PySpark_Streaming_Cat_Temperature")  
ssc = StreamingContext(sc, 300) 
spark = SparkSession(sc)

from io import BytesIO

def decode_image(message):
    return BytesIO(message)

kafkaStream = KafkaUtils.createDirectStream(
    ssc, ["cat_temp_humidity"], {"metadata.broker.list":"x.x.x.x:x"})
	
import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from requests import get
import json

# Kafka offset value
offset_last_value = 0
# Nest current temperature
nest_temperature = 0

def store_offset_value_and_nest_temperature(rdd):
    global offset_last_value
    offset_range = rdd.offsetRanges()
    offset_last_value = offset_range[len(offset_range) - 1].untilOffset
    
    global nest_temperature
    url = 'http://x.x.x.x:x/api/states/climate.living_room'
    headers = {'x-ha-access': 'x',
               'content-type': 'application/json'}

    response = get(url, headers=headers)
    nest_thermostat_state = json.loads(response.text)
    nest_temperature_in_f = nest_thermostat_state['attributes']['temperature']
    # Convert to Celsius
    nest_temperature = (nest_temperature_in_f - 32) * 5.0/9.0

    return rdd
	
def window12(rdd):
    if not rdd.isEmpty():
        df = rdd.toDF()
        df.show(12)

        df.createOrReplaceTempView("df")

        df_avg_temp_diff = spark.sql("""
        SELECT
            AVG(temperature_difference) AS avg_temp_diff
        FROM
        (
            SELECT
                ABS(_1 - _2) AS temperature_difference
            FROM
                df
        ) x
        """)

        df_avg_temp_diff.show(1)
        
        for row in df_avg_temp_diff.rdd.collect():
            avg_temp_diff = row[0]

            # If the moving average of temperature difference is over 3 for 1 hour, send an email alert
            if avg_temp_diff > 3.0:                
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login("x@gmail.com", "x")

                msg = MIMEMultipart()
                msg['Subject'] = "Temperature Weird! (=^･ω･^=)"
                email_from = "x@gmail.com"
                msg['From'] = email_from
                email_to = "x@gmail.com"
                msg['To'] = email_to
                
                text = MIMEText("Cat area's temperature is significantly different from Nest thermostat's current temperature. The average differene=" + str(avg_temp_diff) + " Nest temperature=" + str(nest_temperature))
                msg.attach(text)

                server.sendmail(email_from, email_to, msg.as_string())
                server.quit()

kafkaStream.pprint()
# Retrieve offset value and Nest thermostat current temperature
rowStream = kafkaStream.transform(store_offset_value_and_nest_temperature).map(lambda x: json.loads(x[1])).map(lambda x: (x['temperature'], nest_temperature))

# window for 12 batches (60 minutes)
rowStream.window(3600, 300).foreachRDD(window12)

ssc.start()
ssc.awaitTermination()
