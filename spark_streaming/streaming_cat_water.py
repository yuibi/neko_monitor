import os
os.environ['PYSPARK_SUBMIT_ARGS'] = '--packages org.apache.spark:spark-streaming-kafka-0-8_2.11:2.0.2 pyspark-shell'  

from pyspark import SparkContext 
from pyspark.streaming.kafka import KafkaUtils 
from pyspark.streaming import StreamingContext
from pyspark.sql import SparkSession

sc = SparkContext(appName="PySpark_Streaming_Cat_Water")  
ssc = StreamingContext(sc, 100) 
spark = SparkSession(sc)

from io import BytesIO

def decode_image(message):
    return BytesIO(message)

kafkaStream = KafkaUtils.createDirectStream(
    ssc, ["cat_water"], {"metadata.broker.list":"x.x.x.x:x"}, valueDecoder = decode_image)
	
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

def ssd_image(img, results, i):    
    voc_classes = ['fountain', 'cat']
    
    feeder_list = ['fountain']
    feeder_resolution = np.zeros(1)
    feeder_in_single_image = []

    # Parse the outputs.
    det_label = results[i][:, 0]
    det_conf = results[i][:, 1]
    det_xmin = results[i][:, 2]
    det_ymin = results[i][:, 3]
    det_xmax = results[i][:, 4]
    det_ymax = results[i][:, 5]

    # Get detections with confidence higher than 0.5.
    top_indices = [i for i, conf in enumerate(det_conf) if conf >= 0.5]

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

            #if the detected object is bigger than 400 pixels (e.g. 20 x 20)
            if resolution >= 400:
                feeder_resolution = np.append(feeder_resolution, resolution)

                cropped_img = img[ymin:ymax, xmin:xmax, :]
                feeder_in_single_image.append(cropped_img)

    if len(feeder_in_single_image) > 0:
        max_resolution_index = np.argmax(feeder_resolution)
        ssd_img = np.uint8(feeder_in_single_image[max_resolution_index-1])
    else:
        ssd_img = img

    return ssd_img

def predict_img(numpy_array, orig_numpy_array):
    # Save the original image for attachment
    scipy.misc.imsave('temp_cat_water.jpg', np.uint8(orig_numpy_array))
    
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

    # If the SSD model does not find an appropriate object, automatically return 0.00
    for i, img in enumerate(images):
        if type(results[i]) is not list:
            ssd_img = ssd_image(img, results, i)
            resize_img = imresize(ssd_img, (img_size, img_size))

            x = np.expand_dims(resize_img, axis=0)
            y_pred = model_cnn.predict(x)
            prediction = round(y_pred[0][0], 3)
        else:
            prediction = 0.00
    
    return prediction

# Kafka offset value
offset_last_value = 0

def store_offset_value(rdd):
    global offset_last_value
    offset_range = rdd.offsetRanges()
    offset_last_value = offset_range[len(offset_range) - 1].untilOffset
    
    return rdd
	
def window3(rdd):
    if not rdd.isEmpty():
        df = rdd.toDF()
        df.show(3)

        df.createOrReplaceTempView("df")

        df_avg_score_3 = spark.sql("""
        SELECT
            AVG(_1) AS avg_score_3,
            MIN(_1) AS min_score_3
        FROM
            df
        """)

        df_avg_score_3.show(1)

        for row in df_avg_score_3.rdd.collect():
            avg_score_3 = row[0]
            min_score_3 = row[1]

            # If the moving average is over 0.75 & minimum score of the 3 batches is over 0.5, send an email alert with the image
            if avg_score_3 > 0.75 and min_score_3 > 0.5:                
                server = smtplib.SMTP('smtp.gmail.com', 587)
                server.starttls()
                server.login("x@gmail.com", "x")

                msg = MIMEMultipart()
                msg['Subject'] = "Empty Cat Water! (=^･ω･^=)"
                email_from = "x@gmail.com"
                msg['From'] = email_from
                email_to = "x@gmail.com"
                msg['To'] = email_to
                
                text = MIMEText("Cat water fountain is empty! Average score=" + str(avg_score_3) + " Minimum score=" + str(min_score_3) + " Offset value=" + str(offset_last_value))
                msg.attach(text)
                fp = open('temp_cat_water.jpg', 'rb')                                                    
                img = MIMEImage(fp.read())
                fp.close()
                msg.attach(img)

                server.sendmail(email_from, email_to, msg.as_string())
                server.quit()

kafkaStream.pprint()
# Retrieve offset value, resize an image in 300x300 for SSD & 299x299 for Inception v3, and predict (0 = not empty; 1 = empty)
rowStream = kafkaStream.transform(store_offset_value).map(lambda x: (image.img_to_array(image.load_img(x[1], target_size=(300, 300))), mpimg.imread(x[1], format='jpg'))).map(lambda (x, y): predict_img(x, y)).map(lambda x: (x, ))

# window for 3 batches (5 minutes)
rowStream.window(300, 100).foreachRDD(window3)

ssc.start()
ssc.awaitTermination()
