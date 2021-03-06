import numpy as np
import matplotlib.pyplot as plt
import cv2 as cv
import tensorflow as tf
import seaborn as sns
from tensorflow import keras
from tensorflow.keras import layers
from tensorflow.keras.models import Sequential
from os import listdir
from os.path import isfile, join
from sklearn.svm import SVC
from sklearn.metrics import plot_confusion_matrix, accuracy_score, confusion_matrix, classification_report

# Dictionary for path lookup. We have train, validation, and test sets, each with two folders (pneumonia/normal)
path_dict = {'train': {'normal': 'chest_xray/train/NORMAL/', 'pneumonia': 'chest_xray/train/PNEUMONIA/'},
             'test': {'normal': 'chest_xray/test/NORMAL/', 'pneumonia': 'chest_xray/test/PNEUMONIA/'},
             'validation': {'normal': 'chest_xray/val/NORMAL/', 'pneumonia': 'chest_xray/val/PNEUMONIA/'}}


# Function to load a dataset and return a numpy array of images and their respective labels. Images are resized to
# 150x150

def load_images(subset):
    print('Loading data, subset =', subset)
    pos_path = path_dict[subset]['pneumonia']  # Pneumonia files
    neg_path = path_dict[subset]['normal']  # Normal files
    pos_files = [image for image in listdir(pos_path) if isfile(join(pos_path, image))]
    neg_files = [image for image in listdir(neg_path) if isfile(join(neg_path, image))]
    pos_images = []
    neg_images = []     
    
    # Iterate through file lists and generate data arrays.
    for pos_sample in pos_files:                    
        image = cv.resize(cv.imread(path_dict[subset]['pneumonia'] + pos_sample, cv.IMREAD_GRAYSCALE), (150, 150))
        pos_images.append(image)
    labels = [1] * len(pos_images) # Pneumonia
    
    for neg_sample in neg_files:
        image = cv.resize(cv.imread(path_dict[subset]['normal'] + neg_sample, cv.IMREAD_GRAYSCALE), (150, 150))
        neg_images.append(image)
    labels += [0] * len(neg_images) # Healthy
    
    # Convert images to numpy array
    images = np.concatenate((pos_images, neg_images))
    del pos_images  # For low memory machines
    del neg_images
    return images, labels


def main():
    
    X_train, y_train = load_images(subset='train')
    X_test, y_test = load_images(subset='test')

    # Let's try an SVM directly on the images themselves
    print('Training SVM classifier...')
    n_samples, nx, ny = X_train.shape
    X_train_svm = X_train.reshape((n_samples, nx * ny))
    n_samples, nx, ny = X_test.shape
    X_test_svm = X_test.reshape((n_samples, nx * ny))
    clf = SVC(verbose=True, class_weight='balanced')
    clf.fit(X_train_svm, y_train)
    print('Estimating classifier performance...')
    predictions = clf.predict(X_test_svm)
    print('SVM score:', accuracy_score(y_test, predictions))
    print('Plotting confusion matrix...')
    # Plot confusion matrix
    class_names = ['healthy', 'pneumonia']
    disp = plot_confusion_matrix(clf, X_test_svm, y_test, display_labels=class_names)
    disp.ax_.set_title('Confusion matrix (SVM)')
    plt.show()
    
    # CNN part
    # Load training and validation data into efficient tf.data datasets. Resize each image to 150x150 as in the SVM case 
    batch_size = 32
    img_height = 150
    img_width = 150
    epochs = 16
    
    train_ds = tf.keras.preprocessing.image_dataset_from_directory(
        directory = 'chest_xray/train',
        validation_split = 0.2,
        subset='training',
        seed=123,
        color_mode = 'grayscale',        
        label_mode = 'binary',
        image_size = (img_height, img_width),
        batch_size = batch_size)
    
    val_ds = tf.keras.preprocessing.image_dataset_from_directory(
        directory ='chest_xray/train',       
        subset='validation',
        validation_split=0.2,
        seed=123,
        color_mode = 'grayscale',  
        label_mode = 'binary',     
        image_size = (img_height, img_width),
        batch_size = batch_size)
    
    # Improve I/O performance via tf autotune
    AUTOTUNE = tf.data.AUTOTUNE
    train_ds = train_ds.cache().shuffle(1000).prefetch(buffer_size=AUTOTUNE)
    val_ds = val_ds.cache().prefetch(buffer_size=AUTOTUNE)

    # Normalize data
    normalization_layer = layers.experimental.preprocessing.Rescaling(1./255)
    
    # Data augmentation due to class imbalance
    data_augmentation = keras.Sequential(
      [
        layers.experimental.preprocessing.RandomFlip("horizontal", 
                                                    input_shape=(img_height, 
                                                                  img_width,
                                                                  1)),
        layers.experimental.preprocessing.RandomRotation(0.1),
        layers.experimental.preprocessing.RandomZoom(0.1),
      ]
    )
    # Create a model and train it. Use a single neuron with sigmoid activation, since this is a binary classification problem.
    # Add dropout to ensure good generalization.    
    model = Sequential([    
      data_augmentation,
      layers.experimental.preprocessing.Rescaling(1./255),
      layers.Conv2D(16, 3, padding='same', activation='relu'),
      layers.MaxPooling2D(),
      layers.Conv2D(32, 3, padding='same', activation='relu'),
      layers.MaxPooling2D(),
      layers.Conv2D(64, 3, padding='same', activation='relu'),
      layers.MaxPooling2D(),
      layers.Dropout(0.4),     
      layers.Flatten(),   
      layers.Dense(1, activation='sigmoid')
    ])
    model.compile(optimizer='adam',
              loss=tf.keras.losses.BinaryCrossentropy(),
              metrics=['accuracy'])
    model.summary()
    
    history = model.fit(
      train_ds,
      validation_data=val_ds,
      epochs=epochs
    )
    # Visualize training results
    acc = history.history['accuracy']
    val_acc = history.history['val_accuracy']

    loss = history.history['loss']
    val_loss = history.history['val_loss']

    epochs_range = range(epochs)
  
    plt.figure(figsize=(8, 8))   
    plt.subplot(1, 2, 1)
    plt.plot(epochs_range, acc, label='Training Accuracy')
    plt.plot(epochs_range, val_acc, label='Validation Accuracy')
    plt.legend(loc='lower right')
    plt.title('Training and Validation Accuracy')

    plt.subplot(1, 2, 2)
    plt.plot(epochs_range, loss, label='Training Loss')
    plt.plot(epochs_range, val_loss, label='Validation Loss')
    plt.legend(loc='upper right')
    plt.title('Training and Validation Loss')
    plt.show()
   
    # Test model on unseen test data
    X_test = np.expand_dims(X_test, axis=-1)
    predictions = (model.predict(X_test) > 0.5).astype('int32')
    # Plot confusion matrix and print score    
    print('Classifier score:', accuracy_score(y_test, predictions))
    cm = confusion_matrix(y_test, predictions)
    print('Classification report:', classification_report(y_test, predictions, target_names=['healthy', 'pneumonia']))
    sns.set(font_scale=1.4) # for label size
    sns.heatmap(cm, annot=True, annot_kws={"size": 16}) # font size
    plt.show()

main()
