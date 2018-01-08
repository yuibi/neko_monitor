import os
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-streaming-kafka-0-8_2.11:2.0.2 pyspark-shell'  

from pyspark import SparkContext 
from pyspark.streaming.kafka import KafkaUtils 
from pyspark.streaming import StreamingContext
from pyspark.sql import SparkSession

sc = SparkContext(appName="PySpark_Streaming_Cat_Motion")  
ssc = StreamingContext(sc, 10) 
spark = SparkSession(sc)

from io import BytesIO

def decode_image(message):
    return BytesIO(message)

kafkaStream = KafkaUtils.createDirectStream(
    ssc, ["cat_motion"], {"metadata.broker.list":"x.x.x.x:x"}, valueDecoder = decode_image)
	
from keras.models import load_model
import matplotlib.image as mpimg
from scipy.misc import imresize
from scipy.misc import imread
import numpy as np
import scipy

import cv2
import keras
from keras.applications.imagenet_utils import preprocess_input
from keras.preprocessing import image

from ssd import SSD300
from ssd_utils import BBoxUtility

import smtplib
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from requests import get
import json

def ssd_image(img, results, i):    
    voc_classes = ['fountain', 'cat']
    
    feeder_list = ['cat']
    feeder_resolution = np.zeros(1)
    feeder_in_single_image = []

    # Parse the outputs.
    det_label = results[i][:, 0]
    det_conf = results[i][:, 1]
    det_xmin = results[i][:, 2]
    det_ymin = results[i][:, 3]
    det_xmax = results[i][:, 4]
    det_ymax = results[i][:, 5]

    # Get detections with confidence higher than 0.1.
    top_indices = [i for i, conf in enumerate(det_conf) if conf >= 0.1]

    top_conf = det_conf[top_indices]
    top_label_indices = det_label[top_indices].tolist()
    top_xmin = det_xmin[top_indices]
    top_ymin = det_ymin[top_indices]
    top_xmax = det_xmax[top_indices]
    top_ymax = det_ymax[top_indices]

    for j in range(top_conf.shape[0]):
        xmin = int(round(top_xmin[j] * img.shape[1]))
        ymin = int(round(top_ymin[j] * img.shape[0]))
        xmax = int(round(top_xmax[j] * img.shape[1]))
        ymax = int(round(top_ymax[j] * img.shape[0]))
        score = top_conf[j]
        label = int(top_label_indices[j])
        label_name = voc_classes[label - 1]

        if label_name in feeder_list:
            resolution = (ymax-ymin)*(xmax-xmin)

            #if the detected object is bigger than 100 pixels (e.g. 10 x 10)
            if resolution >= 100:
                feeder_resolution = np.append(feeder_resolution, resolution)

                cropped_img = img[ymin:ymax, xmin:xmax, :]
                feeder_in_single_image.append(cropped_img)

    if len(feeder_in_single_image) > 0:
        return True
    else:
        return False

    return False

def predict_img(numpy_array, orig_numpy_array):
    # Save the original image for attachment
    scipy.misc.imsave('temp_cat_motion.jpg', np.uint8(orig_numpy_array))
    
    # Number of voc_classes + 1
    NUM_CLASSES = 3
    input_shape=(300, 300, 3)
    # SSD model
    model = SSD300(input_shape, num_classes=NUM_CLASSES)
    model.load_weights('./model/weights.18-0.09.hdf5', by_name=True)
    bbox_util = BBoxUtility(NUM_CLASSES)
    
    # Inception v3 transfer learning model
    model_cnn = load_model(filepath='./model/model_v2.03-0.40.hdf5')
    ssd_img_size=300
    img_size=299

    inputs = []
    images = []

    images.append(orig_numpy_array)
    
    inputs.append(numpy_array.copy())
    inputs = preprocess_input(np.array(inputs))
    preds = model.predict(inputs, batch_size=1, verbose=0)
    results = bbox_util.detection_out(preds)

    cat_inside_image = False
    # If the SSD model does not find a cat, return False
    for i, img in enumerate(images):
        cat_inside_image = ssd_image(img, results, i)
    
    return cat_inside_image

# Kafka offset value
offset_last_value = 0

def store_offset_value(rdd):
    global offset_last_value
    offset_range = rdd.offsetRanges()
    offset_last_value = offset_range[len(offset_range) - 1].untilOffset
    
    return rdd
	
def cat_detection(rdd):
    if not rdd.isEmpty():
        # If the cat is not in the image and my car is not home, send an email alert with the image
        for row in rdd.collect():
            cat_inside_image = row[0]
            if not cat_inside_image:
                # Telematics GPS location for my car
                url = 'http://x.x.x.x:x/api/states/device_tracker.2010_toyota_highlander'
                headers = {'x-ha-access': 'x',
                           'content-type': 'application/json'}

                response = get(url, headers=headers)
                telematics_location_state = json.loads(response.text)
                print(telematics_location_state['state'])
                
                if telematics_location_state['state'] == "away":
                    server = smtplib.SMTP('smtp.gmail.com', 587)
                    server.starttls()
                    server.login("x@gmail.com", "x")

                    msg = MIMEMultipart()
                    msg['Subject'] = "Suspicious Motion! (=^･ω･^=)"
                    email_from = "x@gmail.com"
                    msg['From'] = email_from
                    email_to = "x@gmail.com"
                    msg['To'] = email_to

                    text = MIMEText("Suspicous motion was detected!")
                    msg.attach(text)
                    fp = open('temp_cat_motion.jpg', 'rb')                                                    
                    img = MIMEImage(fp.read())
                    fp.close()
                    msg.attach(img)

                    server.sendmail(email_from, email_to, msg.as_string())
                    server.quit()

kafkaStream.pprint()
# Retrieve offset value, resize an image in 300x300 for SSD & 299x299 for Inception v3, and predict (True = cat is in the image; False = the cat is NOT in the image)
rowStream = kafkaStream.transform(store_offset_value).map(lambda x: (image.img_to_array(image.load_img(x[1], target_size=(300, 300))), mpimg.imread(x[1], format='jpg'))).map(lambda (x, y): predict_img(x, y)).map(lambda x: (x, ))

rowStream.foreachRDD(cat_detection)

ssc.start()
ssc.awaitTermination()
